"""Write readable tables and blind review pairs from retained study results."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import random


def percent(value: float | None) -> str:
    return f"{100 * value:.1f}%" if value is not None else "n/a"


def number(value: float | None) -> str:
    return f"{value:,.1f}" if value is not None else "n/a"


def render(report: dict, rows: list[dict]) -> str:
    metadata = report["metadata"]
    lines = [
        "# Context study results",
        "",
        f"Study: `{metadata['study']}`. Runtime: `{metadata['backend']}`. "
        f"Requested model: `{metadata['model']}`. Effort: `{metadata['effort']}`. "
        f"Repetitions: {metadata['repeats']}. Seed: {metadata['seed']}.",
        "",
        f"Run started: {metadata['utc']}. CLI: `{metadata.get('agent_version', 'not used')}`.",
        "",
        "This is a synthetic context study. It does not measure repository task completion or user time saved.",
        "",
        "## Results by condition",
        "",
    ]
    if metadata["backend"] == "retrieval":
        lines += [
            "No inference service was used. No agent quality result is available.",
            "",
        ]
        lines += [
            "| Condition | Source recall | Mean context bytes |",
            "| --- | ---: | ---: |",
        ]
        for condition, stats in report["summary"].items():
            lines.append(
                f"| {condition} | {percent(stats['retrieval_recall'])} | {number(stats['mean_context_bytes'])} |"
            )
        return "\n".join(lines) + "\n"
    lines += [
        "| Condition | Field accuracy | Grounded task success | Context bytes | Input tokens | Cached input | Output tokens | Mean time (s) | Errors |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for condition, stats in report["summary"].items():
        lines.append(
            f"| {condition} | {percent(stats['answer_accuracy'])} | {percent(stats['grounded_task_success'])} "
            f"| {number(stats['mean_context_bytes'])} | {number(stats['mean_input_tokens'])} "
            f"| {number(stats['mean_cached_input_tokens'])} | {number(stats['mean_output_tokens'])} "
            f"| {number(stats['mean_total_seconds'])} | {stats['errors']} |"
        )
    lines += [
        "",
        "Cached input is a subset of input. Time includes process start and service latency.",
        "",
        "| Condition | Incorrect answered fields | Unknown accuracy | Citation rubric mismatch | Questions per run |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for condition, stats in report["summary"].items():
        lines.append(
            f"| {condition} | {percent(stats['incorrect_answer_rate'])} | {percent(stats['unknown_accuracy'])} "
            f"| {percent(stats['invalid_citation_rate'])} | {number(stats['questions_per_run'])} |"
        )
    lines += [
        "",
        "Citation mismatch uses a fixed list. It is not a general source validity check.",
        "",
        "## Results by task",
        "",
        "Values are correct fields / required fields, summed across repetitions. Errors count as zero correct fields.",
        "",
        "| Task | Category | none | plain | brain | oracle |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for task in metadata["tasks"]:
        samples = [r for r in rows if r["task"] == task]
        cells = []
        for condition in ("none", "plain", "brain", "oracle"):
            selected = [r for r in samples if r["condition"] == condition]
            correct = sum(r.get("score", {}).get("correct", 0) for r in selected)
            total = sum(r["slot_count"] for r in selected)
            cells.append(f"{correct}/{total}" if selected else "n/a")
        lines.append(
            f"| {task} | {samples[0]['category']} | " + " | ".join(cells) + " |"
        )
    lines += ["", "## Paired accuracy differences", ""]
    for baseline, interval in report["paired_accuracy"].items():
        if interval:
            low, high = interval["bootstrap_95_percent"]
            lines.append(
                f"- brain minus {baseline}: {100 * interval['mean_task_accuracy_delta']:.1f} percentage points. "
                f"Descriptive task bootstrap interval: {100 * low:.1f} to {100 * high:.1f}."
            )
    lines += [
        "",
        "Intervals describe this fixture. They do not establish a population effect.",
        "",
        "## Failed samples",
        "",
    ]
    errors = [r for r in rows if "error" in r]
    if not errors:
        lines.append("No execution errors were recorded.")
    for row in errors:
        lines.append(
            f"- {row['task']} / {row['condition']} / repetition {row['repetition']}: {row['error']}"
        )
    lines += ["", "## Scored answer mismatches", ""]
    mismatches = [
        r for r in rows if r.get("score") and r["score"]["correct"] != r["slot_count"]
    ]
    for row in mismatches:
        fields = [s["name"] for s in row["score"]["slots"] if not s["correct"]]
        lines.append(
            f"- {row['task']} / {row['condition']} / repetition {row['repetition']}: {', '.join(fields)}. See the retained response."
        )
    if not mismatches:
        lines.append("No scored answer mismatches were recorded.")
    lines += ["", "## Limits", ""]
    lines.extend(f"- {limit}" for limit in metadata["limits"])
    lines += [
        "- Human blind review has not been completed by this report command.",
        "- Short exact answers can hide response-quality differences. Inspect the full responses.",
        "- Fixed synthetic tasks are not a held-out real-world dataset.",
        "",
    ]
    return "\n".join(lines)


def blind_pairs(rows: list[dict], seed: int) -> tuple[list[dict], list[dict]]:
    rng = random.Random(seed)
    groups = {}
    for row in rows:
        groups.setdefault((row["task"], row["repetition"]), {})[row["condition"]] = row
    pending = []
    for (task, repetition), group in groups.items():
        if "brain" not in group:
            continue
        for baseline in ("none", "plain"):
            if baseline in group:
                pair = [group["brain"], group[baseline]]
                rng.shuffle(pair)
                pending.append((task, repetition, pair))
    rng.shuffle(pending)
    pairs, keys = [], []
    for number, (task, repetition, pair) in enumerate(pending, 1):
        identity = f"pair-{number:04d}"
        pairs.append(
            {
                "id": identity,
                "task": pair[0]["prompt"]
                .split("TASK\n", 1)[1]
                .split("\n\nCONTEXT", 1)[0],
                "A": pair[0].get("response", {"error": "No valid response."}),
                "B": pair[1].get("response", {"error": "No valid response."}),
                "review": {"winner": None, "reason": "", "reviewer": ""},
            }
        )
        keys.append(
            {
                "id": identity,
                "task": task,
                "repetition": repetition,
                "A": pair[0]["condition"],
                "B": pair[1]["condition"],
            }
        )
    return pairs, keys


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    report = json.loads((args.directory / "report.json").read_text())
    rows = [
        json.loads(line)
        for line in (args.directory / "runs.jsonl").read_text().splitlines()
    ]
    (args.directory / "RESULTS.md").write_text(render(report, rows))
    if report["metadata"]["backend"] != "retrieval":
        pairs, keys = blind_pairs(rows, report["metadata"]["seed"])
        review = args.directory / "review.jsonl"
        key = args.directory / "review-key.json"
        if not review.exists() and not key.exists():
            review.write_text("".join(json.dumps(p) + "\n" for p in pairs))
            key.write_text(json.dumps(keys, indent=2) + "\n")
    print(args.directory / "RESULTS.md")


if __name__ == "__main__":
    main()
