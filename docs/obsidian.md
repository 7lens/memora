# Live Obsidian vault

Use Obsidian to read and edit local knowledge inside the Memora project.
The `obsidian/` directory is a private editable view of `knowledge/`.
Memora keeps the canonical notes, unknown metadata, revisions, and immutable events.
This adapter is separate from a standard vault export, which remains a snapshot.

## Start

From the repository root, run:

```sh
.venv/bin/memora obsidian start
.venv/bin/memora obsidian status
```

The first start creates the vault and `.obsidian/app.json` settings.
Open **Open folder as vault** in Obsidian and select this project's `obsidian/` directory.
Read `Memora.md` for the note count and pending issues. Open Graph view to explore links.
The adapter uses local files and Obsidian's built-in features.

The local process checks for changes each second. New agent captures, imports, and other memory writes appear automatically.
Editor changes return through the normal Memora write service.
When nothing changes, the process checks file metadata without parsing the full memory.
The background process runs on macOS and Linux. Start it again after a computer restart.
It does not install a login service. Use these commands to stop it or run one synchronization pass:

```sh
.venv/bin/memora obsidian stop
.venv/bin/memora obsidian sync
```

Use `memora obsidian watch` for a foreground process. Its optional `--interval` accepts 0.1 to 60 seconds.
`obsidian status` reports whether a worker runs, its last successful synchronization, errors, and pending issues.
Read `.brain/obsidian/watch.log` if the process cannot start.
Edits stay in the vault until a synchronization pass succeeds.

## Edit

Existing notes have readable file names with a short identity suffix.
You can edit the Markdown body, title, description, tags, sources, and knowledge state.
You can rename a file inside `Notes/`; its identity remains the same.
Keep `memora_id`, `memora_revision`, and the existing note type unchanged.
Use Memora for advanced metadata such as observation subjects, validity, external references, and project scope.
The adapter retains that metadata when you edit other fields.

Use `rel_` properties for typed graph relations. Each property is a list of quoted internal links:

```yaml
rel_depends_on:
  - "[[Notes/Cache policy--12345678]]"
rel_supports: []
```

Keep the actual target file name in each link. Obsidian can complete internal links.
An empty list removes that relation type from the note. A target with no vault note uses a `memora:/path/to/note.md` value.
The footer between `memora:links` markers shows the graph links. Memora generates that footer; edit the properties to change typed relations.
Project scope and observation subjects can also create graph links. Change their source fields through Memora.
Ordinary `[[wiki links]]` in the body remain text in canonical memory. Use `rel_` properties when a link must have a typed Memora relation.

New notes belong in `Notes/`. A plain Markdown note becomes an Idea with pending scope.
Optional YAML properties can specify a type, title, description, tags, sources, state, and relations.
Supported new types are Idea, Concept, Fact, Decision, Procedure, Document, System, and Source.
A Fact needs a source. A Decision must explain its reason in the content.
New notes and edits stay private. They do not approve publication or verify evidence.
Editing approved content makes its publication review stale through the normal write rules.
The audit actor is `process:obsidian`; it does not claim a verified human identity.

Profiles, tasks, checkpoints, events, and local catalogs stay outside the vault.
Attachments remain local vault files. The adapter does not import them into memory or recovery bundles.
Use a sourced Document note for durable document knowledge.

## Resolve a conflict

If Memora and Obsidian change the same note, synchronization stops for that note.
Other valid notes can continue. Neither version overwrites the other automatically.
Malformed properties, unknown identities, duplicate identities, and missing files also need review.
Read `Memora.md` or run `obsidian status` for the issue and current source revision.

Read the canonical note with `memora show ID`. Compare it with the vault file.
Then keep one version explicitly, using the current canonical revision:

```sh
memora obsidian resolve UUID --keep vault --revision 7
memora obsidian resolve UUID --keep memory --revision 7
```

The first command saves the vault content as a new private revision.
The second command restores the canonical content in the vault.
If the canonical revision changes again, resolution stops until you read it again.
To combine both versions, edit the vault content before you choose `--keep vault`.

Removing a vault file does not delete canonical memory.
Use `--keep memory` to restore it. Use the discarded state to retire knowledge with its history intact.
For duplicate identities, keep one file per identity before resolution.
The adapter retains replaced and conflicting editor text under `.brain/obsidian/backups/`.
It checks the editor text again before a projection write. Filesystem writes from arbitrary editors do not share Memora's lock.
Keep backups when you review a concurrent-save issue.

## Privacy and storage

Keep `/knowledge/`, `/obsidian/`, and `.brain/` excluded from Git.
The adapter checks the vault ignore rule and rejects tracked vault files and symbolic links.
The public-tree check also rejects tracked vault content.
The source and vault stay inside the selected local workspace. Synchronization uses local files.
Shared team publication still needs an exact human review through Memora.
For a named space, supply the usual `--workspace NAME` option before `obsidian`.

State under `.brain/obsidian/` records the last synchronized revision and editor content.
Do not remove this state to resolve a conflict. Keep it with the vault until you settle the conflict.
The adapter requires its original state before it uses an existing non-empty `obsidian/` directory.
The earlier external snapshot vault remains separate and receives no live updates.

Obsidian documents [existing vaults](https://obsidian.md/help/vault),
[properties](https://obsidian.md/help/properties), and
[Graph view](https://obsidian.md/help/plugins/graph).
