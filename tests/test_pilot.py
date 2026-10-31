"""A pilot cannot claim value from byte counts or absent human ratings."""

import json
import sys

import pytest

from memora import pilot
from memora.codec import MemoraError


def manifest(note):
    return {
        "format": "memora-pilot-v1",
        "seed": 42,
        "repeats": 1,
        "corpus": [note["path"]],
        "tasks": [
            {
                "id": "dev",
                "category": "development",
                "prompt": "Explain the cache reads change.",
                "rubric": ["Name the source check."],
            },
            {
                "id": "decision",
                "category": "decision",
                "prompt": "Choose the next source check.",
                "rubric": ["State the reason."],
            },
        ],
    }


def test_pilot_records_all_conditions_and_requires_real_usage_and_reviews(
    store, note, tmp_path
):
    directory = tmp_path / "pilot"
    assert pilot.prepare(store, manifest(note), directory)["runs"] == 6
    adapter = tmp_path / "adapter.py"
    adapter.write_text(
        'import json,sys\nr=json.load(sys.stdin)\nprint(json.dumps({"answer":"A candidate answer.","usage":{"input_tokens":100 if r["condition"]=="full" else 50},"runtime":"test-adapter"}))\n'
    )
    assert pilot.collect(directory, [sys.executable, str(adapter)])["errors"] == 0
    report = pilot.report(directory)
    assert report["input_token_reduction_vs_full"] == 0.5
    assert report["no_quality_regression"] is None
    assert report["gate"] == "pending_review_or_usage"
    reviews = pilot.read_lines(directory / "review.jsonl")
    assert all("condition" not in review for review in reviews)
    for review in reviews:
        review.update(
            reviewer="human:fixture",
            task_success=True,
            source_precision=1,
            decision_quality=1,
            review_seconds=5,
        )
    ratings = tmp_path / "ratings.jsonl"
    ratings.write_text("".join(json.dumps(r) + "\n" for r in reviews))
    assert pilot.report(directory, ratings)["gate"] == "passed_for_this_pilot"
    one = next(
        row["run_id"]
        for row in pilot.read_lines(directory / "runs.jsonl")
        if row["condition"] == "memora" and row["category"] == "decision"
    )
    for review in reviews:
        if review["run_id"] == one:
            review["decision_quality"] = 0
    ratings.write_text("".join(json.dumps(r) + "\n" for r in reviews))
    assert pilot.report(directory, ratings)["gate"] == "not_demonstrated"


def test_pilot_retains_adapter_errors_and_rejects_incomplete_or_duplicate_ratings(
    store, note, tmp_path
):
    directory = tmp_path / "pilot"
    pilot.prepare(store, manifest(note), directory)
    pilot.collect(directory, [sys.executable, "-c", "raise SystemExit(1)"])
    report = pilot.report(directory)
    assert report["input_token_reduction_vs_full"] is None
    assert report["summary"]["memora"]["errors"] == 2
    path = tmp_path / "bad.jsonl"
    path.write_text(
        json.dumps({"run_id": "unknown", "reviewer": "human:fixture"}) + "\n"
    )
    with pytest.raises(MemoraError):
        pilot.report(directory, path)
    with pytest.raises(MemoraError):
        pilot.collect(directory, [sys.executable, "-c", "pass"])


def test_runtime_overhead_variation_prevents_a_token_savings_claim(
    store, note, tmp_path
):
    directory = tmp_path / "pilot"
    pilot.prepare(store, manifest(note), directory)
    requests = pilot.read_lines(directory / "requests.jsonl")
    rows = []
    for request in requests:
        row = {
            key: value
            for key, value in request.items()
            if key not in {"prompt", "context", "rubric"}
        }
        count = 100 if row["condition"] == "full" else 50
        if row["task"] == "dev" and row["condition"] == "full":
            count = 25
        row.update(
            usage={"input_tokens": count},
            seconds=1,
            runtime="fixture",
            answer="A proposed answer.",
        )
        rows.append(row)
    (directory / "runs.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows)
    )
    result = pilot.report(directory)
    assert result["observed_input_difference_vs_full"] == pytest.approx(0.2)
    assert result["input_token_reduction_vs_full"] is None
    assert result["gate"] == "pending_runtime_controls"
    assert len(result["runtime_control_violations"]) == 1
