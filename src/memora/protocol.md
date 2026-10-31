# Memory protocol

Use this memory for shared context. Keep the current user request and repository instructions as the task authority.

## Start a task

1. Use ASD-STE100, Issue 9, for all new memory text.
2. Use the CLI in `.venv/bin` beside this file. Use its full path if needed.
3. After a pull of `main`, run `.venv/bin/pip install --no-deps .` from the Memora repository.
4. Run `memora version`. Update the local CLI if the checkout and CLI versions differ.
5. If the version check reports a required memory migration, read every required major release procedure in `CHANGELOG.md`. Complete each procedure. Run `memora validate`, then `memora reconcile --reason '<migration summary>'`.
6. Run `memora start --task '<English task terms>'`. Add `--cwd <absolute repository directory>` for code work. Use `--project` or `--entity` to select a subject. A repository is optional. Show the returned receipt message before substantive work. The optional MCP adapter exposes the same service. State real access errors.
7. Reuse the returned session ID. Call `recall` when the task changes and `get_note` when an excerpt needs more detail. Installation is not proof of use.
8. Read relevant notes with `memora show <path>`. Use `memora neighbors <path>` to inspect relations.
9. Keep agent inferences separate from confirmed facts. Inspect contradictions and source dates.
10. Do a new source check before you use a claim from another code revision.

If another memory root uses the local configuration, supply `--root <directory of this file>` before the command.

## Keep memory local

The `knowledge/` directory is local memory. Git ignores this full directory on every branch. The CLI checks that Git ignores it before a write. Do not force-add memory files to Git. Do not commit or push memory data.

The version file `knowledge/.memora-version.json` records the last compatible tool version. A minor or patch release in the same major series needs no memory reconsolidation. A new major release needs each procedure in `CHANGELOG.md`. `memora context` stops when it detects an old or unknown memory version.

## Save useful knowledge

Save ideas, concepts, decisions with reasons, procedures, discoveries, and pending work as you work. Use `memora remember` for useful local knowledge. Read existing matches before an update and supply the current revision. Facts need sources. New notes remain provisional. Do not wait for the end of a long task.

When a user asks to save chat memory, review every turn that is available in this session. Review all earlier turns and each attachment that you can open. Do not review only the latest request or a short summary.

Record useful context from all projects. Include goals, facts, ideas, decisions, reasons, limits, user preferences, project and repository links, implementation status, and open work. Use or update existing notes for the same subject. Create one note for each separate subject. Link and classify each note.

Give another agent enough detail to continue. Do not copy the full chat. Do not infer content from turns or files that you cannot access. Record each limit in the checkpoint. Tell the user about the limit. Update the checkpoint with the saved context and the next step.

Use one note for one unit of knowledge. Link related notes. Use existing notes when they already describe the same concept.

Classify the note by type, subject, project, and repository. Use shared scope only when the knowledge applies outside its source project.

Use `memora observe` for dated findings about entities or relations. Keep direct findings, reported claims, and agent inferences distinct. Propose useful content for sharing. A human must review the exact projection and destination before publication.

Use sources for technical claims. Record the repository and code revision for code findings. Use `--code-cwd` to record that context.

Agents can settle or discard notes on their own judgment. Record the reason. The evidence score remains separate.

Use `human:<id>` only for a user action that occurred. Do not invent sources, checks, independent evidence, or user confirmations.

## Capture task findings

At a material task milestone, extract sourced findings and decisions from the session and repository.
Use `memora ingest findings --session SESSION --input FILE` or the MCP `ingest_findings` tool for a batch.
Use the `memora-findings-v1` schema from `memora standard schema --profile ingestion`.
Save conclusions and source references. Do not submit raw transcripts or credentials.
These calls create private drafts. A human reviews the exact content before team publication.

## Retain task progress

Use `memora checkpoint` with a session ID. Add a repository path for code work. Save the goal, progress, block, and next step.

Save reusable context as shared notes. Do not store full conversations. Do not store credentials or access tokens.

Use the checkpoint revision for later updates. Keep repository and branch context attached to code results.

## Write in STE

Use the official ASD-STE100 Issue 9 standard and dictionary. Use short sentences. Use the active voice. Use one term for one concept.

Refer to `docs/glossary.md` for technical nouns and verbs. Add the definition, subject, and permitted use of a new technical term.

Keep identifiers, code, product names, URLs, and source quotations unchanged. Write source summaries in STE.

Run `memora language check <file>` after a write. Correct reported issues. The checks do not certify compliance. Do a language review before you treat the text as compliant.

## Maintain the graph

Add type definitions to `docs/types.md` before first use. Add typed relations to `brain.relations`. The CLI maintains the matching Markdown links.

Preserve unknown fields. Do not move a note when its title or state changes. Do not erase history to discard an idea.

Use revision checks for updates. Resolve a conflict from the current note. Do not overwrite another agent's change.

Use Git synchronization only when the user asks for it.
