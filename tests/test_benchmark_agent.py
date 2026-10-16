"""Check the study design and scorer without an inference service."""

import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


@pytest.fixture
def study():
    path = Path(__file__).resolve().parents[1] / "scripts/benchmark_agent.py"
    spec = importlib.util.spec_from_file_location("brain_study", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def reporter():
    path = Path(__file__).resolve().parents[1] / "scripts/report_benchmark.py"
    spec = importlib.util.spec_from_file_location("brain_report", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fixture_retrieves_expected_sources_with_no_private_data(study, tmp_path):
    corpus = json.loads((study.FIXTURE / "corpus.json").read_text())
    tasks = json.loads((study.FIXTURE / "tasks.json").read_text())["tasks"]
    store = study.fixture_store(tmp_path, corpus)
    index = study.Index(store)
    try:
        index.refresh()
        for task in tasks:
            context = study.prepare_context(index, task, corpus, "brain", 12000)
            assert context["recalled"] == context["relevant"], task["id"]
            assert context["bytes"] <= 12000
            assert "old-owner" not in context["selected"]
            prompt = study.make_prompt(task, context["text"])
            assert '"values"' not in prompt
            assert '"expected"' not in prompt
        assert not (tmp_path / "docs").exists()
    finally:
        index.close()


def test_scorer_separates_correctness_sources_and_missing_information(study):
    task = {"expected": {"owner": {"values": ["Willow"], "notes": ["owner"]}}}
    response = {
        "answers": {"owner": {"value": "Willow", "sources": []}},
        "questions": [],
    }
    assert study.grade(task, response, "")["correct"] == 1
    assert not study.grade(task, response, "")["success"]
    response["answers"]["owner"]["sources"] = [study.source_for("owner")]
    assert study.grade(task, response, study.source_for("owner"))["success"]
    assert not study.grade(task, response, "")["success"]
    response["answers"]["owner"]["value"] = "Birch"
    score = study.grade(task, response, study.source_for("owner"))
    assert score["correct"] == 0
    assert score["slots"][0]["answered"]
    task["expected"]["owner"] = {"values": [None], "notes": []}
    response["answers"]["owner"] = {"value": None, "sources": []}
    assert study.grade(task, response, "")["success"]


@pytest.mark.parametrize("bad", [None, {}, {"answers": {}, "questions": []}])
def test_malformed_responses_are_errors(study, bad):
    task = {"expected": {"owner": {"values": ["Willow"], "notes": []}}}
    with pytest.raises(ValueError):
        study.grade(task, bad, "")


def test_failures_remain_in_the_denominator_and_intervals_pair_tasks(study):
    slot = {
        "correct": True,
        "grounded": True,
        "answered": True,
        "unknown_expected": False,
        "invalid_citation": False,
    }
    context = {"bytes": 12, "seconds": 0.1, "recalled": 1, "relevant": 1}
    row = {
        "task": "first",
        "condition": "brain",
        "slot_count": 1,
        "seconds": 2,
        "context": context,
        "score": {"correct": 1, "success": True, "slots": [slot], "questions": 0},
        "usage": {"input_tokens": 7},
    }
    failed = {k: v for k, v in row.items() if k not in {"score", "usage"}}
    failed.update(task="second", error="timeout")
    summary = study.summarize([row, failed])["brain"]
    assert summary["answer_accuracy"] == 0.5
    assert summary["grounded_task_success"] == 0.5
    assert summary["errors"] == 1
    assert summary["mean_input_tokens"] == 7
    baseline = {**failed, "condition": "none", "task": "first"}
    interval = study.paired_interval([row, baseline], "none", 1)
    assert interval["mean_task_accuracy_delta"] == 1
    assert interval["tasks"] == 1
    assert interval["bootstrap_95_percent"] == [1, 1]


def test_codex_runner_rejects_tools_and_sums_usage(study, monkeypatch, tmp_path):
    args = SimpleNamespace(codex="codex", model="fixture", effort="high", timeout=10)
    schema = {"type": "object"}
    response = {"answers": {}, "questions": []}
    events = [
        {
            "type": "item.completed",
            "item": {"type": "agent_message", "text": json.dumps(response)},
        },
        {"type": "turn.completed", "usage": {"input_tokens": 3}},
        {"type": "turn.completed", "usage": {"input_tokens": 4}},
    ]

    def execute(command, **kwargs):
        assert "--ignore-user-config" in command
        assert "project_doc_max_bytes=0" in command
        assert kwargs["input"] == "Question."
        return SimpleNamespace(
            returncode=0, stdout="\n".join(json.dumps(e) for e in events)
        )

    monkeypatch.setattr(study.subprocess, "run", execute)
    assert (
        study.run_codex("Question.", schema, args, tmp_path)["usage"]["input_tokens"]
        == 7
    )
    events.insert(0, {"type": "item.completed", "item": {"type": "command_execution"}})
    with pytest.raises(RuntimeError, match="unexpected item"):
        study.run_codex("Question.", schema, args, tmp_path)


def test_blind_pairs_hide_labels_and_keep_the_review_key_separate(reporter):
    rows = [
        {
            "task": "task-one",
            "condition": condition,
            "repetition": 0,
            "prompt": "TASK\nWho owns this?\nAnswer keys: owner\n\nCONTEXT\nData.",
            "response": {
                "answers": {"owner": {"value": "Example", "sources": []}},
                "questions": [],
            },
        }
        for condition in ("none", "plain", "brain", "oracle")
    ]
    pairs, keys = reporter.blind_pairs(rows, 1701)
    assert len(pairs) == len(keys) == 2
    assert (pairs, keys) == reporter.blind_pairs(rows, 1701)
    assert {k for p in pairs for k in p} == {"id", "task", "A", "B", "review"}
    assert all("CONTEXT" not in p["task"] for p in pairs)
    assert all(p["review"]["winner"] is None for p in pairs)
    assert all("brain" in {k["A"], k["B"]} for k in keys)
    assert {k["id"] for k in keys} == {p["id"] for p in pairs}


def test_retrieval_report_does_not_claim_agent_accuracy(reporter):
    report = {
        "metadata": {
            "study": "fixture",
            "backend": "retrieval",
            "model": None,
            "effort": "high",
            "repeats": 1,
            "seed": 1,
            "utc": "fixture",
        },
        "summary": {"brain": {"retrieval_recall": 1, "mean_context_bytes": 100}},
    }
    result = reporter.render(report, [])
    assert "No agent quality result is available" in result
    assert "Field accuracy" not in result
    assert "100.0%" in result


def test_command_backend_retains_results_and_refuses_to_replace_them(
    study, monkeypatch, tmp_path
):
    adapter = tmp_path / "adapter.py"
    adapter.write_text(
        "import json, sys\n"
        "request = json.load(sys.stdin)\n"
        'assert "expected" not in request\n'
        'keys = request["schema"]["properties"]["answers"]["required"]\n'
        'answers = {key: {"value": None, "sources": []} for key in keys}\n'
        'print(json.dumps({"response": {"answers": answers, "questions": []}}))\n'
    )
    target = tmp_path / "result"
    command = json.dumps([sys.executable, str(adapter)])
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "benchmark_agent.py",
            "--backend",
            "command",
            "--model",
            "fixture-stub",
            "--command-json",
            command,
            "--tasks",
            "missing",
            "--repeats",
            "1",
            "--output",
            str(target),
        ],
    )
    study.main()
    rows = [
        json.loads(line) for line in (target / "runs.jsonl").read_text().splitlines()
    ]
    report = json.loads((target / "report.json").read_text())
    assert len(rows) == 4
    assert report["metadata"]["model"] == "fixture-stub"
    assert report["summary"]["brain"]["grounded_task_success"] == 1
    assert report["summary"]["brain"]["mean_input_tokens"] is None
    assert report["metadata"]["files_sha256"]
    with pytest.raises(SystemExit) as exc:
        study.main()
    assert exc.value.code == 2


def test_command_failure_is_recorded_without_a_retry(study, monkeypatch, tmp_path):
    target = tmp_path / "failure"
    command = json.dumps([sys.executable, "-c", "raise SystemExit(3)"])
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "benchmark_agent.py",
            "--backend",
            "command",
            "--model",
            "fixture-stub",
            "--command-json",
            command,
            "--tasks",
            "missing",
            "--conditions",
            "brain",
            "--repeats",
            "1",
            "--output",
            str(target),
        ],
    )
    with pytest.raises(SystemExit) as exc:
        study.main()
    assert exc.value.code == 1
    rows = (target / "runs.jsonl").read_text().splitlines()
    assert len(rows) == 1
    assert "error" in json.loads(rows[0])
    stats = json.loads((target / "report.json").read_text())["summary"]["brain"]
    assert stats["errors"] == 1
    assert stats["answer_accuracy"] == 0
    assert stats["grounded_task_success"] == 0
