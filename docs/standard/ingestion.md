# Agent capture

Agents extract conclusions from task sessions, code changes, and documents.
The agent performs extraction. Memora validates and stores the findings; it does not start an inference service or read chat logs.
At a material task milestone, call `ingest_findings` through MCP or run the CLI command below.
Editor instructions provide this workflow. A receipt records a call, not guaranteed editor hook execution.

```sh
memora ingest evidence --cwd /absolute/repository --file docs/architecture.md
memora ingest findings --session SESSION --input /private/findings.json --preview
memora ingest findings --session SESSION --input /private/findings.json
```

Use `memora standard schema --profile ingestion` for the input schema.
Use this shape for extracted conclusions:

```json
{
  "format": "memora-findings-v1",
  "findings": [{
    "type": "Decision",
    "title": "Keep source authority",
    "description": "Use Markdown as the local source.",
    "body": "Use Markdown because people and agents can inspect it.",
    "reason": "Keep the design reason.",
    "sources": [{"resource": "urn:example:design-review"}],
    "tags": ["architecture"]
  }]
}
```

Every finding needs a reason. A Fact needs a source. A Decision must state its reason in the body.
The evidence command returns a tracked file identity, Git revision, and file hash. It returns no source text.
The hash describes current file bytes; a working tree can differ from its commit.
The session supplies project and repository scope. A batch cannot select another session scope.
Updates need the existing path and revision. Read matching notes before an update.

A preview validates and stages the entire batch without saving notes.
A malformed finding prevents the entire batch from being saved.
Equal title and content in the same scope need no change. Different content under the same title needs review.
The journal permits recovery of notes and immutable events after an interrupted write.
The service records the session receipt after the note batch commits.

Raw transcript fields are not accepted. The capture boundary rejects common credential patterns, URL credentials, and explicit chat transcripts.
These checks cover selected patterns. The extracting agent must omit secrets and unnecessary personal data before submission.
Do not send complete source files in a finding. Link the source and save the conclusion.
All captures remain private and provisional. No ingestion operation publishes content or verifies evidence.
