# Context study results

Study: `context-study-v1`. Runtime: `codex`. Requested model: `gpt-6-luna`. Effort: `high`. Repetitions: 3. Seed: 1701.

Run started: 2026-10-16T20:02:11.846177+00:00. CLI: `codex-cli 0.162.0-alpha.17.2`.

This is a synthetic context study. It does not measure repository task completion or user time saved.

## Results by condition

| Condition | Field accuracy | Grounded task success | Context bytes | Input tokens | Cached input | Output tokens | Mean time (s) | Errors |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| none | 27.8% | 16.7% | 0.0 | 10,465.1 | 2,112.0 | 105.9 | 4.4 | 0 |
| plain | 100.0% | 100.0% | 4,833.0 | 11,640.4 | 3,754.7 | 97.8 | 4.5 | 0 |
| brain | 98.1% | 97.2% | 2,507.0 | 11,008.8 | 2,112.0 | 117.1 | 4.5 | 0 |
| oracle | 96.3% | 94.4% | 252.2 | 10,519.4 | 2,816.0 | 85.6 | 4.3 | 0 |

Cached input is a subset of input. Time includes process start and service latency.

| Condition | Incorrect answered fields | Unknown accuracy | Citation rubric mismatch | Questions per run |
| --- | ---: | ---: | ---: | ---: |
| none | 0.0% | 100.0% | 0.0% | 0.4 |
| plain | 0.0% | 100.0% | 9.3% | 0.0 |
| brain | 2.4% | 100.0% | 0.0% | 0.0 |
| oracle | 4.8% | 100.0% | 0.0% | 0.0 |

Citation mismatch uses a fixed list. It is not a general source validity check.

## Results by task

Values are correct fields / required fields, summed across repetitions. Errors count as zero correct fields.

| Task | Category | none | plain | brain | oracle |
| --- | --- | ---: | ---: | ---: | ---: |
| preferences | personal context | 0/6 | 6/6 | 6/6 | 6/6 |
| decision | previous decision | 0/6 | 6/6 | 5/6 | 4/6 |
| handoff | task continuation | 0/6 | 6/6 | 6/6 | 6/6 |
| relations | related context | 0/6 | 6/6 | 6/6 | 6/6 |
| change | changed knowledge | 0/3 | 3/3 | 3/3 | 3/3 |
| expiry | expired knowledge | 3/3 | 3/3 | 3/3 | 3/3 |
| conflict | contradictory knowledge | 3/3 | 3/3 | 3/3 | 3/3 |
| procedure | procedure | 0/6 | 6/6 | 6/6 | 6/6 |
| business | business context | 0/6 | 6/6 | 6/6 | 6/6 |
| inference | unverified inference | 3/3 | 3/3 | 3/3 | 3/3 |
| missing | missing knowledge | 3/3 | 3/3 | 3/3 | 3/3 |
| self-contained | self-contained control | 3/3 | 3/3 | 3/3 | 3/3 |

## Paired accuracy differences

- brain minus none: 56.9 percentage points. Descriptive task bootstrap interval: 30.6 to 81.9.
- brain minus plain: -1.4 percentage points. Descriptive task bootstrap interval: -4.2 to 0.0.
- brain minus oracle: 1.4 percentage points. Descriptive task bootstrap interval: 0.0 to 4.2.

Intervals describe this fixture. They do not establish a population effect.

## Failed samples

No execution errors were recorded.

## Scored answer mismatches

- preferences / none / repetition 1: language, bullet_count. See the retained response.
- decision / none / repetition 0: pattern, atomic_changes. See the retained response.
- handoff / none / repetition 2: next_test, blocker. See the retained response.
- relations / none / repetition 1: vendor, owner. See the retained response.
- relations / none / repetition 0: vendor, owner. See the retained response.
- preferences / none / repetition 2: language, bullet_count. See the retained response.
- procedure / none / repetition 0: first_action, target. See the retained response.
- change / none / repetition 1: owner. See the retained response.
- decision / oracle / repetition 1: atomic_changes. See the retained response.
- relations / none / repetition 2: vendor, owner. See the retained response.
- decision / none / repetition 1: pattern, atomic_changes. See the retained response.
- handoff / none / repetition 0: next_test, blocker. See the retained response.
- change / none / repetition 2: owner. See the retained response.
- decision / none / repetition 2: pattern, atomic_changes. See the retained response.
- change / none / repetition 0: owner. See the retained response.
- procedure / none / repetition 2: first_action, target. See the retained response.
- procedure / none / repetition 1: first_action, target. See the retained response.
- preferences / none / repetition 0: language, bullet_count. See the retained response.
- handoff / none / repetition 1: next_test, blocker. See the retained response.
- business / none / repetition 2: excludes, owner. See the retained response.
- decision / brain / repetition 2: atomic_changes. See the retained response.
- business / none / repetition 1: excludes, owner. See the retained response.
- decision / oracle / repetition 0: atomic_changes. See the retained response.
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
