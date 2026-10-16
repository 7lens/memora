# Context study results

Study: `context-study-v1`. Runtime: `codex`. Requested model: `gpt-6-luna`. Effort: `high`. Repetitions: 1. Seed: 1701.

Run started: 2026-10-16T19:57:55.822417+00:00. CLI: `codex-cli 0.162.0-alpha.17.2`.

This is a synthetic context study. It does not measure repository task completion or user time saved.

## Results by condition

| Condition | Field accuracy | Grounded task success | Context bytes | Input tokens | Cached input | Output tokens | Mean time (s) | Errors |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| none | 27.8% | 16.7% | 0.0 | 10,464.4 | 704.0 | 116.4 | 4.5 | 0 |
| plain | 94.4% | 91.7% | 4,833.0 | 11,640.9 | 704.0 | 97.8 | 4.3 | 0 |
| brain | 100.0% | 100.0% | 2,507.0 | 11,010.2 | 0.0 | 114.0 | 4.5 | 0 |
| oracle | 94.4% | 91.7% | 252.2 | 10,519.5 | 704.0 | 89.7 | 4.0 | 0 |

Cached input is a subset of input. Time includes process start and service latency.

| Condition | Incorrect answered fields | Unknown accuracy | Citation rubric mismatch | Questions per run |
| --- | ---: | ---: | ---: | ---: |
| none | 0.0% | 100.0% | 0.0% | 0.6 |
| plain | 7.1% | 100.0% | 11.1% | 0.0 |
| brain | 0.0% | 100.0% | 0.0% | 0.0 |
| oracle | 7.1% | 100.0% | 0.0% | 0.0 |

Citation mismatch uses a fixed list. It is not a general source validity check.

## Results by task

Values are correct fields / required fields, summed across repetitions. Errors count as zero correct fields.

| Task | Category | none | plain | brain | oracle |
| --- | --- | ---: | ---: | ---: | ---: |
| preferences | personal context | 0/2 | 2/2 | 2/2 | 2/2 |
| decision | previous decision | 0/2 | 1/2 | 2/2 | 1/2 |
| handoff | task continuation | 0/2 | 2/2 | 2/2 | 2/2 |
| relations | related context | 0/2 | 2/2 | 2/2 | 2/2 |
| change | changed knowledge | 0/1 | 1/1 | 1/1 | 1/1 |
| expiry | expired knowledge | 1/1 | 1/1 | 1/1 | 1/1 |
| conflict | contradictory knowledge | 1/1 | 1/1 | 1/1 | 1/1 |
| procedure | procedure | 0/2 | 2/2 | 2/2 | 2/2 |
| business | business context | 0/2 | 2/2 | 2/2 | 2/2 |
| inference | unverified inference | 1/1 | 1/1 | 1/1 | 1/1 |
| missing | missing knowledge | 1/1 | 1/1 | 1/1 | 1/1 |
| self-contained | self-contained control | 1/1 | 1/1 | 1/1 | 1/1 |

## Paired accuracy differences

- brain minus none: 58.3 percentage points. Descriptive task bootstrap interval: 25.0 to 83.3.
- brain minus plain: 4.2 percentage points. Descriptive task bootstrap interval: 0.0 to 12.5.
- brain minus oracle: 4.2 percentage points. Descriptive task bootstrap interval: 0.0 to 12.5.

Intervals describe this fixture. They do not establish a population effect.

## Failed samples

No execution errors were recorded.

## Scored answer mismatches

- preferences / none / repetition 0: language, bullet_count. See the retained response.
- change / none / repetition 0: owner. See the retained response.
- relations / none / repetition 0: vendor, owner. See the retained response.
- decision / none / repetition 0: pattern, atomic_changes. See the retained response.
- handoff / none / repetition 0: next_test, blocker. See the retained response.
- decision / oracle / repetition 0: atomic_changes. See the retained response.
- procedure / none / repetition 0: first_action, target. See the retained response.
- decision / plain / repetition 0: atomic_changes. See the retained response.
- business / none / repetition 0: excludes, owner. See the retained response.

## Limits

- Synthetic context questions, not repository implementation tasks.
- Queries and answer rubrics are fixed in advance and visible to maintainers.
- Gold answers are never sent to the agent; context comes from fixture notes only.
- The runner supplies context. It does not test autonomous CLI discovery or memory capture.
- One response per task; questions receive no reply. No human time savings are measured.
- No monetary cost estimate. Token counts can include cache hits.
- Plain context sends the whole corpus without the Agent Brain byte limit.
- Fixture setup and indexing time are reported separately from per-task time.
- Human blind review has not been completed by this report command.
- Short exact answers can hide response-quality differences. Inspect the full responses.
- Fixed synthetic tasks are not a held-out real-world dataset.
