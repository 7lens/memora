# Context study resources

Read [the study guide](../docs/benchmark.md) for the question, measures, commands, and limits.

## Fixture

- [Corpus](context-v1/corpus.json): 20 fictional notes, their sources, states, and relations.
- [Tasks](context-v1/tasks.json): 12 tasks, retrieval queries, answer keys, and a fixed rubric.

These files contain public test data. They do not contain exported personal memory or customer
information. Source URNs name records in this fixture. They do not establish facts about a real
person, project, vendor, or contract.

The runner creates a separate temporary memory from the corpus for each study. Every model call
starts a fresh session. The runner supplies the task, the response shape, and one context condition.
It does not send the expected answer values to the model.

Keep the `context-study-v1` fixture unchanged when comparing runs. A new task, rubric, or corpus
requires a new study version. Retain old results and explain the change. More repetitions of the
same fixture test stability; they do not add new task types.

## Results

- [Initial pilot](results/2026-10-16-codex-pilot/RESULTS.md): 48 Codex calls, one repetition.
- [Pilot review](results/2026-10-16-codex-pilot/REVIEW.md): literal scoring limits and interpretation.
- [Repeated study](results/2026-10-16-codex-study/RESULTS.md): 144 Codex calls, three repetitions.
- [Study review](results/2026-10-16-codex-study/REVIEW.md): answer audit, input cost, and conclusions.

Each result directory contains the raw prompts, answers, source selection, metrics, settings,
and file hashes. It also contains randomized pairs for a later human review. A generated pair
file does not mean that review has occurred.

The raw scores retain correct paraphrases that the fixed string rubric rejects. Read the review
with the table. A literal match rate is not a complete measure of answer quality.
