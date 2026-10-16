# System structure

`knowledge/` contains the local OKF bundle. Git ignores the full directory on every branch. The public repository does not track memory data. The CLI checks this ignore rule before it writes to the bundle.

`knowledge/.memora-version.json` records the latest tool version that passed memory reconciliation. `memora context` allows a different minor or patch version in the same major series. It blocks context when a major version changed or the memory has no version marker. An agent must follow each major procedure in `CHANGELOG.md`, validate the graph, and run `memora reconcile` before it loads task context.

Each current note has a stable path. A change event stores the before and after content. These records permit reconstruction without a database.

The CLI writes a recovery journal before it changes a note or adds an event. It keeps a local lock during the change. A later command completes an interrupted transaction when the file hashes permit it.

A content hash binds a check to a note. State changes do not change that hash. Content and source changes do change it.

The search index stores current metadata, text, and graph edges. A warm search reads changed files only. The directory scan uses file metadata to detect external changes.

Project and repository scope creates a `belongs_to` graph edge. The scope fields remain the source of truth. A shared note sets `brain.scope` to `shared`. An unknown scope uses `pending` until an agent links a project or repository.

Typed relations use `docs/relations.md`. Add a definition before use. `memora validate` reports missing subject tags, pending scope, unknown relation types, and unresolved targets.

Context packets contain short descriptions and source references. The default limit is 12,000 UTF-8 bytes. This limit is not a model token count.

`memora view` serves the local memory viewer from loopback. The page checks for repository changes every 2.5 seconds and updates its data without a page reload. The view preserves active filters, node positions, and the selected note. It groups notes by project or repository; unscoped notes appear in a shared group.

The viewer receives graph metadata and at most 1,000 recent event summaries. Full note text is loaded on selection. Review metadata contains the selected sharing projection. Canvas renders at most 500 nodes and 2,000 edges. The list view sorts results and shows 50 notes per page. It provides keyboard access. `memora view` is the only viewer command.

Global editor instructions contain one pointer to `START.md`. They do not grant file access. A real editor session must confirm access.

The chat memory protocol reviews all turns and accessible attachments in the current session. It saves useful context as linked notes. It keeps enough detail for another agent to continue. It does not copy a transcript or claim access to missing context.

Source snapshots retain their original bytes. These files can contain text outside STE. New summaries and explanations must use STE.


Read `docs/knowledge.md` for stable identities, observation subjects, isolated spaces, and reviewed projections. CLI and local HTTP actions use the same knowledge functions and Store transactions. MCP is an optional adapter. Remote synchronization uses a separate authenticated provider boundary.

The viewer renders full note content with raw HTML disabled. Writes use the same canonical store as the CLI. Editing checks the loaded revision and preserves unknown fields and events. The client retains form state across background refresh. See [the viewer guide](viewer.md) for the interface and browser checks.
