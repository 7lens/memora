# Repeated study review

## Execution

The study ran 12 tasks × 4 conditions × 3 repetitions: 144 fresh Codex sessions. The requested model
was `gpt-6-luna`, with high reasoning effort. The seed was 1701. Every call returned a response.
No execution error, retry, or unexpected tool event occurred.

The runner, fixture, queries, rubric, model, and effort match the initial pilot. The recorded file
hashes match the retained source files. No retrieval or scoring change followed the pilot.
The corpus contains fictional data only.

An agent inspected the answer variants, each literal mismatch, and each citation mismatch against
the task and supplied sources. The reviewer could see the condition labels. This is not an
independent or blind human review. The generated human review forms remain blank.

## What the automatic result says

| Condition | Correct fields / required fields | Fully grounded tasks / all tasks |
| --- | ---: | ---: |
| No context | 15/54 | 6/36 |
| Full plain notes | 54/54 | 36/36 |
| Agent Brain | 53/54 | 35/36 |
| Ideal selection | 52/54 | 34/36 |

These are literal rubric results. They remain unchanged in `runs.jsonl`, `report.json`, and
`RESULTS.md`. The paired intervals in the report also use these original literal scores.

## Correct paraphrases that the rubric rejects

All three answer mismatches with context concern `decision.atomic_changes`:

| Condition | Repetition, starting at zero | Returned value | Source |
| --- | ---: | --- | --- |
| Ideal selection | 0 | an event and its database change | urn:brain-study:queue-choice |
| Ideal selection | 1 | an event and its database change | urn:brain-study:queue-choice |
| Agent Brain | 2 | an event and its database change | urn:brain-study:queue-choice |

The rubric accepts `event and database change` and the reverse order. The source says that an
event and its database change must commit together. The three answers express that same rule.
The review accepts their meaning. It finds no semantic error among the answers with context.
This is an agent review finding, not a new automatic score or an independent quality estimate.

The five plain-text citation mismatches concern the relation task. Those answers cite the Parcel
application note as well as the routing service note. The application note establishes the
dependency. The service note supplies the vendor and owner. The narrow rubric lists only the
service note. These extra citations support the requested dependency path. They are not invented
or unavailable sources.

The literal scorer needs a new version before it can measure small quality differences reliably.
Use separate fields for atomic changes, or a reviewed semantic rubric. Do not amend this version's
answers after a run. Keep this result as evidence of that measurement limit.

## Available context and missing context

All three conditions with context recover the required project facts and preferences on review.
They give the expected null for expired, conflicting, missing, and unconfirmed claims. They also
complete the arithmetic control. This small fixture shows no useful quality difference among
these three conditions.

Without context, the agent abstains from project facts it cannot know. It supplies no incorrect
non-null answer. It answers the arithmetic control. It also returns null in the four cases that
require that answer. These are useful abstentions. They cannot recover the facts needed for the
other seven tasks. The low task completion result does not imply a tendency to invent facts.

Several questions require fixture-only information. The expected gap against no context follows
from this design. It establishes recovery of supplied context on these tasks, not a general
advantage over another equally informed agent workflow.

## Input size and time

Agent Brain supplies 2,507 context bytes on average. Full notes supply 4,833 bytes. The reduction
is 48.1%. Mean input counts are 11,008.8 and 11,640.4 tokens: a 5.4% reduction. Runtime instructions
contribute to the input count, so the byte and token percentages differ.

The ideal condition uses only 252.2 context bytes on average. Agent Brain always includes the
profile and adds packet metadata, evidence, sources, and selection reasons. These have a cost.
The arithmetic control needs none of this context. The fixture shows that an empty or smaller
context can be sufficient for some tasks.

Mean task time rounds to 4.5 seconds for both Agent Brain and full notes. Cache use differs across
conditions. The study does not establish faster work or a monetary saving. It does not include
the time to capture and review the original notes.

## Conclusions and next work

The useful result is context recovery with less input than a full note dump on this fixture.
The study does not establish higher answer quality than full notes. It also does not establish
faster repository work, fewer bugs, or a return on memory capture time.

The 12 synthetic tasks have strong query overlap with a small corpus. Three repetitions improve
the stability check but do not add independent task types. The intervals describe this fixture.
They cannot establish an effect for an unseen task population.

Next, freeze a new rubric and add held-out variants, larger corpora, real code tasks, and business
deliverables. Give both agents the same source documents in an active tool-use study. Measure
search, capture, review, follow-up questions, task completion, and total effort across new chats.
Complete the blind human review and test more than one model before a broad product claim.
