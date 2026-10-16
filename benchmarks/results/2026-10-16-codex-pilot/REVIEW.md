# Pilot review

This pilot used one response per task and condition: 48 fresh Codex sessions. The requested model
was `gpt-6-luna` with high reasoning effort. All calls returned a response. This review used the
task, context, source text, and condition labels. An agent performed the review. It is not a blind
human review.

## Literal answer limits

The `decision` task expects `event and database change` or `database change and event`.
Both `plain` and `oracle` returned `an event and its database change`. Their source is
`urn:brain-study:queue-choice`. The source states the same rule. The added articles do not change
the meaning. Both answers are correct on inspection, although the literal scorer rejects them.

The automatic tables retain these failures. They do not establish a factual accuracy advantage
for Agent Brain over full notes or ideal selection. The review found no semantic error in the
answers with context. This finding does not replace the recorded automatic scores.

The plain relation answer cites both the application note and the service note. The former
establishes the dependency. The latter supplies the requested values. The extra application
citation has a useful role, although the narrow citation list counts it as a mismatch.

## Initial interpretation

Without context, the agent returns null for missing project facts. It invents no non-null answer.
It answers the arithmetic control and returns the expected null for unknown, expired, conflicting,
and unconfirmed claims. These abstentions are appropriate, but they do not recover the missing
facts needed for seven other tasks.

All three conditions with context provide the requested values on inspection. Agent Brain uses
2,507 context bytes on average, compared with 4,833 for the full corpus: 48.1% fewer bytes.
Its mean input count is 11,010.2 tokens, compared with 11,640.9: 5.4% fewer tokens.
The ideal selection uses much less context than Agent Brain. Always returning the profile and
including packet metadata add overhead.

Mean time is 4.5 seconds with Agent Brain and 4.3 seconds with full notes. This pilot does not show
a time saving. Cache use differs across conditions. No price or productivity claim follows.

One response per condition cannot establish stability. The repeated study retains the same
fixture, prompts, rubric, model, and effort. It does not tune retrieval or the scorer from this pilot.
