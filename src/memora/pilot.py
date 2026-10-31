"""Prepare controlled real-task comparisons and report measured, reviewed outcomes."""

from __future__ import annotations

import json
import random
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from statistics import mean

from .codec import MemoraError, digest, dump, json_text, now
from . import knowledge as k
from .standard import LOCAL_TYPES
from .store import Store, atomic

CONDITIONS = ("none", "full", "memora")


def prepare(store, manifest: dict, output: Path, max_bytes=12000) -> dict:
    if (
        set(manifest) != {"format", "tasks", "corpus", "repeats", "seed"}
        or manifest["format"] != "memora-pilot-v1"
    ):
        raise MemoraError(
            "Use a memora-pilot-v1 manifest with tasks, corpus, repeats, and seed."
        )
    tasks = manifest["tasks"]
    if (
        not isinstance(tasks, list)
        or not tasks
        or not isinstance(manifest["corpus"], list)
        or not manifest["corpus"]
    ):
        raise MemoraError("The pilot needs tasks and an explicit note corpus.")
    if (
        type(manifest["repeats"]) is not int
        or not 1 <= manifest["repeats"] <= 20
        or type(manifest["seed"]) is not int
    ):
        raise MemoraError("Use 1 to 20 repetitions and an integer seed.")
    ids = set()
    for task in tasks:
        if (
            not isinstance(task, dict)
            or set(task) != {"id", "category", "prompt", "rubric"}
            or not all(
                isinstance(task[field], str) and task[field].strip()
                for field in ("id", "prompt")
            )
            or task["category"] not in {"development", "decision"}
            or not isinstance(task["rubric"], list)
            or not task["rubric"]
            or not all(
                isinstance(rule, str) and rule.strip() for rule in task["rubric"]
            )
        ):
            raise MemoraError(
                "Each pilot task needs an ID, category, prompt, and a review rubric."
            )
        if task["id"] in ids:
            raise MemoraError("Pilot task IDs must be unique.")
        ids.add(task["id"])
    if {task["category"] for task in tasks} != {"development", "decision"}:
        raise MemoraError(
            "Include both development and decision tasks with equal reporting weight."
        )
    output = output.expanduser().absolute()
    if output.exists() or output.resolve().is_relative_to(store.root):
        raise MemoraError("Use a new private pilot directory outside the workspace.")
    with store.lock():
        rows = [k.find(store, identity) for identity in manifest["corpus"]]
        if len({data["brain"]["id"] for _, data, _ in rows}) != len(rows) or any(
            data["type"] in LOCAL_TYPES for _, data, _ in rows
        ):
            raise MemoraError(
                "Select distinct knowledge records; omit personal and activity records."
            )
        corpus = [
            {"path": path, "content": dump(data, body)} for path, data, body in rows
        ]
    full = "\n\n".join(item["content"] for item in corpus)
    requests = []
    with tempfile.TemporaryDirectory(prefix="memora-pilot-") as folder:
        stage = Store(Path(folder))
        for item in corpus:
            atomic(stage.path(item["path"]), item["content"])
        from .compatibility import record_baseline
        from .service import MemoryService

        record_baseline(
            stage, "process:pilot", "Use the selected corpus for a private comparison."
        )
        service = MemoryService(stage)
        for task in tasks:
            packet = service.context(task["prompt"], max_bytes=max_bytes)
            for repetition in range(manifest["repeats"]):
                for condition in CONDITIONS:
                    context = {"none": "", "full": full, "memora": packet["text"]}[
                        condition
                    ]
                    requests.append(
                        {
                            "run_id": uuid.uuid4().hex,
                            "task": task["id"],
                            "category": task["category"],
                            "repetition": repetition,
                            "condition": condition,
                            "prompt": task["prompt"],
                            "context": context,
                            "context_bytes": len(context.encode()),
                            "context_sha256": digest(context),
                            "rubric": task["rubric"],
                        }
                    )
    random.Random(manifest["seed"]).shuffle(requests)
    output.mkdir(parents=True, mode=0o700)
    atomic(
        output / "manifest.json",
        json_text(
            {
                **manifest,
                "corpus_sha256": digest(json_text(corpus)),
                "max_bytes": max_bytes,
                "prepared_at": now(),
            }
        ),
    )
    atomic(output / "corpus.json", json_text(corpus))
    atomic(
        output / "requests.jsonl",
        "".join(json_text(request) + "\n" for request in requests),
    )
    return {
        "path": str(output),
        "runs": len(requests),
        "privacy": "private corpus and review artifacts",
        "measurement": "No model usage or quality has been measured.",
    }


def read_lines(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def collect(directory: Path, command: list[str], timeout=180) -> dict:
    if (
        not isinstance(command, list)
        or not command
        or any(not isinstance(part, str) or not part for part in command)
    ):
        raise MemoraError(
            "The adapter must be an explicit JSON array of command arguments."
        )
    output = directory / "runs.jsonl"
    if output.exists():
        raise MemoraError(
            "Pilot runs already exist. Keep them and prepare a new pilot."
        )
    requests = read_lines(directory / "requests.jsonl")
    runs = []
    for request in requests:
        start = time.monotonic()
        row = {
            key: value
            for key, value in request.items()
            if key not in {"context", "prompt", "rubric"}
        }
        try:
            completed = subprocess.run(
                command,
                input=json_text(request),
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
            )
            if completed.returncode:
                raise ValueError("Adapter failed")
            response = json.loads(completed.stdout)
            usage = response["usage"]
            if not isinstance(response.get("answer"), str) or not isinstance(
                usage, dict
            ):
                raise ValueError("Invalid adapter result")
            for key in ("input_tokens", "cached_input_tokens", "output_tokens"):
                if usage.get(key) is not None and (
                    type(usage[key]) is not int or usage[key] < 0
                ):
                    raise ValueError("Invalid token usage")
            row.update(
                answer=response["answer"],
                usage=usage,
                runtime=response.get("runtime", "unspecified"),
            )
        except (ValueError, KeyError, TypeError, OSError, subprocess.TimeoutExpired):
            row["error"] = "The adapter failed or returned an invalid result."
        row["seconds"] = time.monotonic() - start
        runs.append(row)
        # Retain every failure and completed sample if a later run is interrupted.
        atomic(output, "".join(json_text(run) + "\n" for run in runs))
    blinded = [
        {
            "run_id": run["run_id"],
            "task": next(r["prompt"] for r in requests if r["run_id"] == run["run_id"]),
            "rubric": next(
                r["rubric"] for r in requests if r["run_id"] == run["run_id"]
            ),
            "answer": run.get("answer"),
            "error": run.get("error"),
            "reviewer": None,
            "task_success": None,
            "source_precision": None,
            "decision_quality": None,
            "review_seconds": None,
        }
        for run in runs
    ]
    random.Random(0).shuffle(blinded)
    atomic(
        directory / "review.jsonl", "".join(json_text(row) + "\n" for row in blinded)
    )
    return {
        "runs": len(runs),
        "errors": sum("error" in run for run in runs),
        "review": str(directory / "review.jsonl"),
    }


def report(directory: Path, ratings: Path | None = None) -> dict:
    requests = read_lines(directory / "requests.jsonl")
    rows = read_lines(directory / "runs.jsonl")
    expected = {row["run_id"] for row in requests}
    if (
        len(expected) != len(requests)
        or {row["run_id"] for row in rows} != expected
        or len(rows) != len(expected)
    ):
        raise MemoraError(
            "The pilot does not contain exactly one result per prepared run."
        )
    prepared = {row["run_id"]: row for row in requests}
    for row in rows:
        if any(
            row.get(key) != prepared[row["run_id"]].get(key)
            for key in (
                "task",
                "category",
                "condition",
                "repetition",
                "context_sha256",
                "context_bytes",
            )
        ):
            raise MemoraError("A result does not match its prepared request.")
    runtimes = {row.get("runtime") for row in rows if "error" not in row}
    if len(runtimes) > 1:
        raise MemoraError(
            "Use the same runtime and model configuration for each condition."
        )
    reviews = read_lines(ratings) if ratings else []
    scored = {}
    for review in reviews:
        identity = review.get("run_id")
        if (
            identity not in expected
            or identity in scored
            or not isinstance(review.get("reviewer"), str)
            or not review["reviewer"].strip()
        ):
            raise MemoraError(
                "Each review needs one known run ID and a named reviewer."
            )
        if (
            type(review.get("task_success")) is not bool
            or not all(
                type(review.get(field)) in (int, float) and 0 <= review[field] <= 1
                for field in ("source_precision", "decision_quality")
            )
            or type(review.get("review_seconds")) not in (int, float)
            or review["review_seconds"] < 0
        ):
            raise MemoraError(
                "Complete success, source precision, decision quality, and review time for each run."
            )
        scored[identity] = review
    summary = {}
    for condition in CONDITIONS:
        sample = [row for row in rows if row["condition"] == condition]
        counts = [row.get("usage", {}).get("input_tokens") for row in sample]
        outputs = [row.get("usage", {}).get("output_tokens") for row in sample]
        cached = [row.get("usage", {}).get("cached_input_tokens") for row in sample]
        complete = len(scored) == len(expected)
        summary[condition] = {
            "runs": len(sample),
            "errors": sum("error" in row for row in sample),
            "mean_input_tokens": mean(counts)
            if counts and all(value is not None for value in counts)
            else None,
            "mean_context_bytes": mean(row["context_bytes"] for row in sample),
            "mean_output_tokens": mean(outputs)
            if outputs and all(value is not None for value in outputs)
            else None,
            "mean_cached_input_tokens": mean(cached)
            if cached and all(value is not None for value in cached)
            else None,
            "mean_total_tokens": mean([i + o for i, o in zip(counts, outputs)])
            if counts and all(value is not None for value in counts + outputs)
            else None,
            "mean_seconds": mean(row["seconds"] for row in sample),
            "development_success": mean(
                scored[row["run_id"]]["task_success"] and "error" not in row
                for row in sample
                if row["category"] == "development"
            )
            if complete
            else None,
            "decision_quality": mean(
                scored[row["run_id"]]["decision_quality"] if "error" not in row else 0
                for row in sample
                if row["category"] == "decision"
            )
            if complete
            else None,
            "source_precision": mean(
                scored[row["run_id"]]["source_precision"] if "error" not in row else 0
                for row in sample
            )
            if complete
            else None,
            "mean_review_seconds": mean(
                scored[row["run_id"]]["review_seconds"] for row in sample
            )
            if complete
            else None,
        }
        if complete:
            summary[condition]["joint_quality"] = (
                summary[condition]["development_success"]
                + summary[condition]["decision_quality"]
            ) / 2
    full, selected = summary["full"], summary["memora"]
    observed_difference = (
        1 - selected["mean_input_tokens"] / full["mean_input_tokens"]
        if full["mean_input_tokens"] and selected["mean_input_tokens"] is not None
        else None
    )
    pairs = {}
    for row in rows:
        pairs.setdefault((row["task"], row["repetition"]), {})[row["condition"]] = row
    controls = []
    for (task, repetition), pair in pairs.items():
        empty = pair["none"].get("usage", {}).get("input_tokens")
        for condition in ("full", "memora"):
            count = pair[condition].get("usage", {}).get("input_tokens")
            if empty is not None and count is not None and count < empty:
                controls.append(
                    {
                        "task": task,
                        "repetition": repetition,
                        "condition": condition,
                        "reason": "A nonempty context used fewer total input tokens than the empty control. Runtime overhead or internal turn counts may differ.",
                    }
                )
    saving = observed_difference if not controls else None
    complete = len(scored) == len(expected)
    no_regression = (
        all(
            selected[key] >= full[key]
            for key in ("development_success", "decision_quality", "source_precision")
        )
        if complete
        else None
    )
    passed = (
        saving is not None
        and saving > 0
        and no_regression is True
        and not selected["errors"]
    )
    return {
        "phase": "baseline",
        "summary": summary,
        "input_token_reduction_vs_full": saving,
        "no_quality_regression": no_regression,
        "observed_input_difference_vs_full": observed_difference,
        "runtime_control_violations": controls,
        "context_byte_reduction_vs_full": 1
        - selected["mean_context_bytes"] / full["mean_context_bytes"]
        if full["mean_context_bytes"]
        else None,
        "gate": "pending_runtime_controls"
        if controls
        else "passed_for_this_pilot"
        if passed
        else "pending_review_or_usage"
        if not complete or saving is None
        else "not_demonstrated",
        "weight": {"development": 0.5, "decision": 0.5},
        "limits": [
            "Runtime counts are adapter reports. Context bytes are not tokens.",
            "Review labels do not authenticate reviewers.",
            "Capture, maintenance, and human review cost need separate measurement before a productivity claim.",
            "Set confirmation thresholds after this baseline. Do not tune them on the confirmation task set.",
            "A token difference cannot establish retrieval savings when runtime overhead changes across the empty and nonempty conditions.",
        ],
    }
