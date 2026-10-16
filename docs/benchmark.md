# Memora context study

## Question and scope

Does stored context help a new agent session complete a task? Does Memora select useful
context with less input than a full set of notes?

This study uses fictional data. It does not read `knowledge/`, connect to a remote workspace, or
start MCP. The public fixture contains 20 notes and 12 tasks. Each task starts a new agent session.
The fixture includes personal preferences, a previous decision, unfinished work, and a dependency.
It also includes changed ownership, an expired source, conflicting reports, a procedure, and a
business definition. An agent hypothesis, missing knowledge, and an arithmetic control complete the set.

The first study tests short context questions. It does not test code changes, autonomous tool
selection, memory capture, or a full workday. A local Codex process uses remote inference. This
is not a test of a model that runs entirely on the local machine.

Read the [144-call result](../benchmarks/results/2026-10-16-codex-study/RESULTS.md) and its
[review](../benchmarks/results/2026-10-16-codex-study/REVIEW.md). The original
[48-call pilot](../benchmarks/results/2026-10-16-codex-pilot/RESULTS.md) remains available.

## Conditions

| Condition | Input in addition to the task | Purpose |
| --- | --- | --- |
| `none` | No stored context | Measure a fresh chat without stored context. |
| `plain` | All fixture notes as text, with their sources and metadata | Control for access to the same information without retrieval. |
| `brain` | A context packet from Memora text and graph retrieval | Measure the selected context, source warnings, and byte cost. |
| `oracle` | Only the notes listed as relevant by the task rubric | Show a reference with ideal selection. This is not a deployable retriever. |

The same task, response schema, model, reasoning effort, and time limit apply to all conditions.
The runner changes only the supplied context. It randomizes task and condition order with a
recorded seed. Each call starts a fresh session. It never resumes a previous chat.

The `plain` condition retains old and unrelated notes. Memora can exclude superseded notes.
Plain text includes the same state and relation metadata, so the agent can make its own choice.
The full text has no byte limit. The default Memora packet has a 12,000-byte limit. A byte
count is not a token count.

The corpus and rubric are public. Expected answers are not placed in the model prompt. The runner
uses prewritten English queries. The relation task also uses an explicit entity. Results therefore
include a supplied retrieval query and scope; they do not measure an agent's ability to select them.
Several tasks require facts that exist only in the fixture. The baseline cannot know these facts.
This measures recovery of supplied knowledge. The queries have strong word overlap with the notes.
The fixture does not test broad paraphrases, multilingual tasks, or retrieval from a large corpus.

## Measures

| Measure | Definition | Limit |
| --- | --- | --- |
| Answer accuracy | Correct answer fields / all required answer fields | Exact normalized values from a fixed rubric. A valid paraphrase can fail. |
| Grounded task success | Tasks where every field is correct and has the required source / all tasks | A source match is not a general proof of entailment. |
| Incorrect answer rate | Incorrect non-null fields / non-null fields | This is a factual-error proxy, not a general hallucination detector. |
| Unknown accuracy | Correct null fields / fields whose correct answer is unknown | Correct abstention is useful. It does not complete a missing-context task. |
| Citation rubric mismatch | Fields with unlisted or unavailable citations / scored fields | A citation outside the fixed list can still be useful. Inspect the answer. |
| Questions per run | Number of clarification questions in the response | The runner supplies no replies. This does not measure human time saved. |
| Retrieval recall | Relevant notes selected / relevant notes listed in the rubric | Small fixed corpus. Empty relevance sets do not add to the denominator. |
| Context bytes | UTF-8 bytes of the supplied context | Includes headers and sources. Excludes the task and agent instructions. |
| Input and output tokens | Counts reported by the agent runtime | Report cache hits separately. Unknown counts remain null. |
| Task time | Context selection time plus agent wall time | Includes process start and service latency. Corpus setup is separate. |

Malformed output, tool use, a service error, or a timeout remains in the success and accuracy
denominators as a failure. The runner does not retry a failed sample. Rates that need a parsed
response describe parsed responses only. Read the separate error count before use.

Answers use short strings and source URNs. The scorer ignores case, whitespace, and a final full
stop. It accepts only the alternatives specified before the run. Do not change the rubric to make
a result pass. If a rubric needs a correction, retain the old result, give the study a new version,
and describe the reason.

## Run without an inference service

From the repository root:

```sh
PYTHONPATH=src .venv/bin/python scripts/benchmark_agent.py \
  --backend retrieval --repeats 1 --output exports/study-retrieval
```

This command builds temporary memory and checks source selection for all four conditions. It
does not call a model. Its report contains no agent success or accuracy result. It is a check of
the retrieval path, not evidence that an agent completed a task.

## Run with Codex

Install and authenticate the Codex CLI first. Run the study with an explicit available model:

```sh
PYTHONPATH=src .venv/bin/python scripts/benchmark_agent.py \
  --backend codex --model gpt-6-luna --effort high \
  --repeats 3 --seed 1701 --output exports/study-codex
```

Three repetitions produce 144 agent calls: 12 tasks × 4 conditions × 3 repetitions. A pilot can use
`--repeats 1`. The command uses the existing Codex login. It does not copy authentication files.
It records the requested model, CLI version, source file hashes, platform, and settings. A model
alias and its service can change; these fields cannot fix the provider's internal implementation.

Codex uses `--ephemeral` and `--ignore-user-config`. The runner disables project instruction files,
memory, shell tools, plugins, apps, and agent delegation. It also disables web search.
Each call uses an empty temporary work directory. An unexpected tool event fails the sample.
This isolation prevents the installed Memora instructions from giving the baseline memory.
It is an execution control, not an operating system security boundary against a hostile model.

Codex streams structured events with `--json`; `--output-schema` sets the response shape. See the
[official non-interactive execution guide](https://learn.chatgpt.com/docs/non-interactive-mode).
The study follows the use of fixed tasks, explicit criteria, and retained failures described in
the [official evaluation guide](https://developers.openai.com/api/docs/guides/evaluation-best-practices).

## Use another local agent

The command backend accepts a JSON array of command arguments. It uses no shell interpolation.
For example:

```sh
PYTHONPATH=src .venv/bin/python scripts/benchmark_agent.py \
  --backend command --model your-exact-model-id \
  --command-json '["/absolute/path/to/adapter"]' \
  --repeats 3 --output exports/study-other-agent
```

The adapter receives one JSON object on stdin with `prompt` and `schema`. It returns one JSON
object on stdout with `response` and optional `usage`. Diagnostics go to stderr. The response
must follow the schema. Usage can include `input_tokens`, `cached_input_tokens`, and `output_tokens`.
The adapter must start a new session, prevent access to personal memory, and record its model and
runtime outside the prompt. Do not put credentials in command arguments.

## Inspect and review

Each output directory contains `runs.jsonl` and `report.json`. Each run includes the task identity,
condition, repetition, exact prompt, context, source selection, answer, score, tokens, and time.
The report retains errors. Existing output directories are never replaced.

```sh
.venv/bin/python scripts/report_benchmark.py exports/study-codex
```

The report command writes a summary by condition and task. It also prepares randomized answer
pairs for human review. Keep `review-key.json` closed during the review. Review correctness,
unsupported claims, useful uncertainty, and task usefulness. Mark ties and explain the reason.
The automatic result does not imply that a person reviewed the pairs.

The paired interval resamples tasks, after it averages repetitions for each task and condition.
It is a descriptive 95% bootstrap interval for this small fixture. It does not establish a result
for an unseen task population. A single repetition does not measure run-to-run stability.

## Conclusions that the study can support

Compare Memora with both `none` and `plain`. Better answers than `none` can show the value of
available context. Better results than `plain`, or equal results with less input, can show useful
selection on this fixture. Compare with `oracle` to find selection or formatting overhead.

If the arithmetic control gets worse, inspect interference from unrelated context. If a missing
fact produces an invented answer, inspect unsupported claims. If an expired or conflicting source
produces a confident value, inspect the warning and the agent response.

Do not claim developer productivity, fewer bugs, or money saved from these context questions.
Model tokens include fixed runtime instructions. A reduction in context bytes need not produce
the same percentage reduction in tokens, time, or price. Service cache hits and run order can
change latency. No monetary estimate is part of this study.

## Next studies

Before a broad claim, add held-out task variants and larger corpora. Keep tuning and evaluation
sets separate. Use at least five repetitions and more than one model. Add an active tool-use
study with the same raw documents available in both conditions. Measure how the agent searches,
writes memory, resumes work, and corrects bad memory.

Add repository tasks with hidden behavior checks and blind human review. Include business tasks
with a fixed review rubric. Record initial capture and review time. Measure total user effort
across the initial task and later chats. Include stale and misleading memory, private-space
isolation, and tasks that do not need memory. Retain negative results.
