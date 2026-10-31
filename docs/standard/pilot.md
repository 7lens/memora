# Real-task value pilot

Compare the same tasks with no stored context, the full selected corpus, and Memora retrieval.
Use both development work and team decisions. Give the two categories equal weight.
Use actual project tasks and fixed rubrics. The examples are templates, not measured results.

```sh
memora pilot prepare --manifest /private/tasks.json --output /private/pilot --max-bytes 12000
memora pilot run --directory /private/pilot --adapter-json '["python3", "/path/to/runtime-adapter.py"]'
memora pilot report --directory /private/pilot
memora pilot report --directory /private/pilot --ratings /private/completed-review.jsonl
```

The manifest format is `memora-pilot-v1`. It has tasks, an explicit corpus of note paths or IDs, repeats, and seed.
Each task has id, category (`development` or `decision`), prompt, and a list of rubric criteria.
Read `examples/pilot/manifest.json` for a sample.
Only the selected corpus enters the trial. The pilot rejects activity and personal records.
The prepared manifest retains a corpus digest, task rubrics, retrieval limit, and random seed.
Requests retain context hashes and exact context. The preparation step randomizes the order of conditions.
Use a new output directory. All artifacts are private.

An adapter reads one JSON request from stdin. It returns JSON with `answer`, `usage`, and `runtime`.
Usage has input_tokens, cached_input_tokens, and output_tokens, when the runtime reports them.
Unknown counts remain null. Cached input is part of input; do not add it again.
The command is an explicit argument array and runs without a shell.
`scripts/pilot_codex.py` is an optional isolated Codex adapter. It uses remote inference and the configured account.
It disables tools and model memory to compare the supplied context. It records the CLI version and runtime counts.
This adapter tests engineering reasoning and decision support. It does not implement code changes or measure a full workday.
Use a repository-execution adapter and independent acceptance checks for code-edit productivity studies.

The run keeps errors and failed samples. It never converts context bytes into tokens.
Review artifacts omit condition labels. A human completes the rubric for each answer.
Use task_success for the development acceptance criteria. Use decision_quality on a scale from 0 to 1.
A score of 1 means all decision criteria are met. A score of 0 means the answer fails the task.
Source precision is the fraction of checked factual claims supported by the cited sources.
Record review_seconds. Keep unsupported, stale, and contradicted claims in the review.
A reviewer label is a report, not authentication.

Without complete reviews and runtime usage, the result is pending.
A baseline shows value only for that task set.
Memora must use fewer input tokens than full context.
Development success, decision quality, and source precision must not decrease.
Record the no-context condition too. Lower quality than no context requires investigation even if token use falls.
Set confirmation thresholds after the baseline. Freeze them before the held-out confirmation run.
Do not tune retrieval or thresholds on the confirmation task set.

Record capture tokens, maintenance time, and human review effort separately before a net cost or productivity claim.
A small reasoning pilot cannot establish team-wide savings or better business outcomes.
The original synthetic study under `benchmarks/` remains unchanged.

Compare each nonempty condition with its empty control for the same task.
If total input falls below the empty control, the report keeps the observed counts but blocks a retrieval-savings claim.
Pin the model and runtime instructions, or retain complete turn accounting, before a confirmation run.
The packet-only adapter does not follow `get_note` links. Test progressive retrieval separately before a workflow claim.
