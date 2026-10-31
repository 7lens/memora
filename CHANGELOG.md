# Changelog

Record each public release here. Keep the tool version in `pyproject.toml` and `src/memora/__init__.py` in sync.

Every release must state its memory action. Minor and patch releases in one major series must say that no reconsolidation is needed. A major release must include ordered steps that an agent can apply to old memory. Keep each major procedure so an agent can migrate across more than one major release.

## [1.6.1] - 2026-10-31

- Memory action: `none`.
- No reconsolidation is required. Existing memory remains readable.
- Replace directory ownership with a kernel file lock that releases on process exit.
- Support nested operations in one thread and preserve exclusion across threads, processes, and forked children.
- Keep bounded waits, transaction recovery, and expected revision checks.
- Archive a legacy lock only when the operating system confirms that its owner has stopped.
- Keep the doctor cleanup option compatible without removing a kernel lock file.
- Stop old long-running Memora clients before the update. Restart them with the installed version.

## [1.6.0] - 2026-10-31

- Memory action: `none`.
- No reconsolidation is required. Existing memory remains readable.
- Add a private live Obsidian vault inside each local workspace.
- Synchronize new memory and editor changes with a local background process.
- Keep expected revisions, immutable events, unknown metadata, and publication review rules.
- Retain both versions of a conflict and require explicit resolution against the current revision.
- Keep standard vault exports as separate snapshots. Knowledge Standard 1.0.0 does not change.

## [1.5.0] - 2026-10-31

- Memory action: `none`.
- No reconsolidation is required. Existing memory remains readable.
- Add Memora Knowledge Standard 1.0.0, schemas, a validator, and conformance fixtures.
- Add JSON-LD/PROV-O exchange and Obsidian vault export for reviewed projections.
- Retain provenance in new publication reviews. Keep existing v1 and v2 writers compatible.
- Add private batch capture of extracted findings through CLI and MCP.
- Retain sources, stable identities, expected revisions, and immutable events.
- Add the portable remote profile, 7lens integration, and a real-task pilot protocol.

## [1.4.1] - 2026-10-16

- Memory action: `none`.
- Rename the project, Python package, CLI, viewer, and editor integration to Memora.
- Use `memora` and `python -m memora` for all new commands.
- Read existing memory version markers and private bundles. Keep note identities and history.
- Keep the `brain` frontmatter namespace and exchange fields compatible with existing data.
- Keep original study records unchanged. Their historical labels identify the measured software.

## [1.4.0] - 2026-10-16

### Memory compatibility

- Memory action: `none`.
- No reconsolidation is required. Existing notes remain readable.

### Changes

- Add a portal layout with light and dark themes, memory counts and quick views.
- Read full Markdown content when a user selects a note. Keep raw HTML inactive.
- Separate content, evidence, relations and history in the inspector.
- Add note editing with revision checks. Keep open forms during live refresh.
- Add capture for concepts, facts, decisions and procedures.
- Keep the root workspace selector when the CLI opens a named space.

## [1.3.0] - 2026-10-16

### Memory compatibility

- Memory action: `none`.
- No reconsolidation is required. Existing notes remain readable.

### Changes

- Add an optional authenticated API connector with explicit push and pull.
- Add public-client PKCE login, machine credentials, private token files and logout.
- Add canonical v2 exchange, incremental cursors, withdrawal handling and conflict resolution.
- Keep local context available without MCP or a remote provider.
- Keep existing v1 local exchange readable. No major memory migration is required.

## [1.2.0] - 2026-10-16

### Memory compatibility

- Memory action: `none`.
- No reconsolidation is required. Existing notes remain readable.
- Run `memora migrate` for a preview. Run `memora migrate --apply` to assign stable identities.
- Apply keeps a full copy under `.brain/backups/` and records normal change events.
- Keep immutable events and unknown fields. Existing shared scope remains private across projects.

### Changes

- Use the CLI by default. Install MCP only with the optional extra and transport flag.
- Add stable entity and relation IDs, dated observations, profiles, and context without a repository.
- Add personal and team spaces, context feedback, and pending work from earlier sessions.
- Add reviewed selective exchange without private history or task progress.
- Add full note reading, capture, relations, and review in the local viewer.

## [1.1.0] - 2026-10-12

### Memory compatibility

- Memory action: `none`.
- Reconsolidation is not required. Existing notes and events retain their identities.
- New external references are optional. Session receipts stay in local cache files.

### Changes

- Add a local MCP server and task session receipts.
- Rank task context by relevance and return note excerpts.
- Add optional local semantic search with a fixed model revision.
- Add private graph bundles with conflict reports and import recovery.
- Configure MCP and steering together. Show session calls in the live viewer.
- Prepare external references for a future private external-graph connector. No remote sync exists.

## [1.0.1] - 2026-10-07

### Memory compatibility

- Memory action: `none`.
- This patch improves the live viewer and removes static HTML export.
- No memory fields, entity paths, or relations change. Reconsolidation is not required.

## [1.0.0] - 2026-10-06

### Memory compatibility

- Memory action: `baseline`.
- This release sets the first memory version baseline.
- Versions from `1.0.0` through `1.x` do not need memory reconsolidation.
- A memory with no version marker needs a one-time review before use.

### Reconsolidation procedure

1. Update the local CLI from the current checkout.
2. Run `memora version` and confirm that the checkout and CLI versions match.
3. Review the entity types, scopes, sources, and relations in the current memory.
4. Run `memora validate`. Fix each error and warning.
5. Run `memora reconcile --reason '<summary of the review>'`.
6. Run `memora version`. Confirm that the memory and tool use the same major version.

No memory fields or entity paths change in this release.

## Release procedure

For each future release, add a section above this procedure.

- A minor or patch release must state that reconsolidation is not required.
- A major release must state why reconsolidation is required.
- A major release must give exact steps for every data or relation change.
- Keep every major procedure. Agents must apply all procedures between the stored and current major versions.
- Test version detection, context blocking, and reconciliation before release.
