# Durable context and observations

Memora keeps useful context between chats. It works without a repository, a model service, or an MCP process. Run `memora view` only when you need the local interface. Keep new summaries and interface text in ASD-STE100, Issue 9. Retain source quotations in their original language.

## One model, three purposes

- An `Entity` names a subject. Its `brain.entity_kind` can be `person`, `organization`, `service`, `asset`, `system`, or another defined subject kind.
- Knowledge notes keep concepts, facts, decisions, procedures, and source summaries. An `Observation` records a dated claim about an entity or relation.
- A `Checkpoint` keeps task progress. A `Profile` keeps personal preferences and goals. Neither type can enter a shared projection.

Each new note has a UUID in `brain.id`. Each explicit typed relation has a UUID in `brain.relations[].id`. Its `target_id` names the target; `target` is a local path hint. The index resolves IDs after a file moves. IDs cannot change during an update. The index rejects repeated identities. Markdown is authoritative; SQLite and viewer edges are projections.

The relation catalog can define `description`, `origin_types`, and `target_types` instead of a text definition. The relation command checks those endpoint types. The `observes` edge comes from an observation subject. Scope edges come from project and repository fields. These derived edges do not create a second stored relation.

```sh
brain entity --kind service --title 'Payments' --description 'The payment service.' --reason 'Keep the service context.'
brain entity --kind organization --title 'Example vendor' --description 'The service vendor.' --reason 'Keep the vendor context.'
memora relate SUBJECT_ID VENDOR_ID --type depends_on --revision 1 --reason 'Record the dependency.'
memora observe --subject SUBJECT_ID --title 'Support status' --predicate support_status \
  --value '"supported"' --basis reported --source https://example.org/support \
  --observed-at 2026-10-16T10:00:00Z --reason 'Keep the source claim.'
```

An observation has `subject` (`kind` and UUID), `predicate`, JSON `value`, `author`, `observed_at`, and `basis`. `valid_until` is optional. The basis is `direct`, `reported`, or `inferred`. Direct and reported observations need sources. An inferred observation remains marked as an inference and has an evidence score of at most 25. A publication review never increases the evidence score.

Use `--subject-kind relation --subject RELATION_ID` to describe a relation. Use `contradicts` to keep conflicting observations. Use `replaces` for a later observation. Retain both records and their sources. Derive a durable Fact or Decision from the observation with `derived_from`. A state change or source check uses the existing revision and event rules.

## Start another chat

```sh
memora capture --type Profile --title 'Working preferences' --description 'My work preferences.' \
  --body 'Use short status updates. Explain decisions.' --source human:owner \
  --scope shared --tag preferences --reason 'Keep my preferences.'
memora start --task 'review service vendor dependencies'
memora start --task 'review service vendor dependencies' --entity SUBJECT_ID
memora recall --session SESSION_ID --task 'support status and open work'
memora feedback --session SESSION_ID --path NOTE_PATH --outcome used --reason 'This decision guided the task.'
```

Add `--project PROJECT_PATH` or `--cwd /absolute/repository` when needed. With no selected repository or project, retrieval can search the selected workspace. A repository task retains its project boundaries. A task includes up to two eligible Profile notes, relevant knowledge, and matching unfinished checkpoints from earlier sessions. Profile excerpts share the normal 12,000-byte budget. Source changes, expiry, and code revisions remain visible.

Feedback can be `used`, `corrected`, or `irrelevant`. It records the returned note revision. It is an agent report, not proof of understanding and not source verification. It does not alter knowledge evidence or search ranks automatically.

## Personal and team spaces

```sh
memora workspace create research --kind personal
memora workspace create team --kind team
memora workspace list
memora --workspace team start --task 'review support status'
memora --workspace team view
```

A workspace has separate Markdown, events, sessions, and indexes. Named spaces stay under `.brain/workspaces/`. The default personal memory stays in `knowledge/`. The old `brain.scope: shared` still means across projects in that space. It does not publish a note or grant access to another person.

These are local data boundaries, not authenticated team permissions. Select a space in the viewer or CLI. A remote provider must enforce its own owners and team permissions.

## Propose, review, and share

```sh
memora share propose NOTE_PATH --revision 1 --destination team --actor agent:local \
  --body 'The selected context for this team.' --reason 'This context helps the team.'
memora share preview NOTE_PATH
memora share approve NOTE_PATH --revision 2 --actor human:owner --reason 'I reviewed this exact content and destination.'
memora share export --destination team --output /private/path/team-context.json
memora --workspace team share import /private/path/team-context.json
```

The proposal contains the exact public projection: title, description, selected body, safe source references, identity, and observation data when present. Review all of it. Export excludes local source paths, arbitrary source metadata, checkpoints, profiles, receipts, and private event snapshots. Export includes only approved records for one destination. It includes a relation only after approval of both endpoints. Include the observation subject too. Content changes require a new proposal and approval.

The package has an integrity checksum, not a digital signature. Import validates the full package before changes and uses a recovery journal. Equal records are idempotent. Divergent incoming or local content requires review. Import does not silently overwrite it. Imported review labels do not authenticate a person and do not count as source verification.

The viewer supports subject capture, observations, typed relations, full note reading, proposal previews, approval, and downloads. It binds to loopback. Writes require a same-origin request and a per-process token. Revision conflicts leave the stored note intact. It is not a hosted multiuser service.

## Migrate existing memory

Run `memora migrate` first. It reports the notes that need identities and changes no notes. Run `memora migrate --apply` to apply the change. The command copies the full knowledge directory into `.brain/backups/ID/knowledge` before the first write. It preserves unknown fields and existing immutable events. Each migrated note receives a normal revision event. Run `memora validate` after migration.

For recovery, stop all writers, retain the current knowledge directory, and restore the backup knowledge directory to its original location. Keep the current `.brain` directory for inspection and remove its disposable index before a new `memora reindex`. Never copy only part of a backup over live notes. An interrupted apply can resume through the existing write journal; rerun migration to finish the remaining notes.

New notes use identities without migration. Existing notes remain readable. Version 1.2 needs no major memory reconciliation.
