# Private memory and future connectors

Memora stores local memory and exchanges reviewed projections between local spaces. The optional remote adapter exchanges approved knowledge through an authenticated API. Personal memory stays outside Git. See [remote transfer](remote.md) for the current adapter. Private full-memory bundles remain local.

## External references

Optional `brain.external_refs` connect a note to a typed external entity:

```yaml
brain:
  external_refs:
    - provider: external-graph
      instance: customer-installation-id
      entity_type: platform
      entity_id: payments
      relation: documents
      observed_revision: '4'
```

Each reference needs provider, instance, entity type, entity ID, and relation strings. The observed revision
is optional text. Keep one identifier for one entity. A note can have many references. A reference
is not a copied asset, an access grant, or proof that the entity exists. The local viewer shows an
external node and a typed edge. It labels the entity unchecked until a future connector checks it.

Use an instance identifier that distinguishes customer installations. Entity IDs alone are not
sufficient. Future connectors must use the authorized API rather than database credentials.
Deleting an external entity must not delete its personal notes. A connector must report broken
references and retain the last observed revision.

## Private bundles

```sh
brain bundle export /private/path/memory.json
brain bundle import /private/path/memory.json
```

Export writes a new file outside the software repository. Treat it as private user data. It
contains all note content, references, and immutable events. It excludes machine configuration,
credentials from configuration, model files, indexes, and session receipts. Text that a user placed
inside a note remains in the bundle. Keep credentials out of notes.

The `memora-private-v1` JSON bundle contains a brain UUID, note identities, bundle paths,
SHA-256 checksums, raw Markdown notes, and raw immutable events. A stable note identity combines
its origin brain UUID and bundle path. Import retains this identity when another local brain
exports the note. Checksums detect content damage; they are not digital signatures.

Import validates the full package before changes. Equal content is idempotent. A linear advance
needs an exact local snapshot in the incoming history. Divergent content or different identities
at one path produces a private conflict report. Import refuses the full package if any entry conflicts.
An interrupted import has a local recovery journal. Recovery refuses an unrelated external edit.
Custom entity types must exist in the local type catalog before import. Register local repository
paths after import because machine paths are not part of the package configuration.

## Future private-memory provider boundary

A future transport can exchange this versioned bundle and a remote revision or cursor. It must
retain note identity, revision, unknown fields, typed relations, sources, and immutable events.
It can pull private memory and push changes with an expected remote revision.
It can resolve an external reference through the user's authorized view. Conflicts require review;
there is no silent last-write-wins policy. Local CLI and MCP remain usable when the provider fails.

A remote backend must derive the memory owner from authenticated identity. It must not trust a
user ID sent by an agent. Every read, write, list, search, and back-reference must enforce that
owner's private namespace. Linking a private note to a shared Service or Platform must not expose
the note to other users. Corporate role inheritance must not make personal memory public.
Team publication uses the reviewed projection contract below. These access checks and
remote protocols belong to the later provider integration work. Local bundle metadata does not
provide encryption or remote access enforcement.

## Reviewed knowledge exchange v1

`context-knowledge-v1` is distinct from a private backup bundle. Its top-level fields are:

- `format`: `context-knowledge-v1`.
- `destination`: the selected target space identifier.
- `records`: approved projections.
- `relations`: directed relations between selected records.
- `sha256`: SHA-256 of the canonical JSON of the other fields. Canonical JSON uses sorted keys, UTF-8, and the Python JSON default separators.

Each record has a UUID `id`, `type`, `title`, `description`, `body`, and `sources` (resource references only). `Entity` also has `entity_kind`. Optional `external_refs` contain only the reviewed provider, instance, entity type, entity ID, relation, and observed revision fields. `Observation` also has `observation`: a subject UUID and entity/relation kind, predicate, JSON value, author, basis, observation time, and optional validity end. `origin` has the workspace identifier and local revision. `review` has the reviewer label and approval time. These labels are provenance, not authorization credentials.

Each relation has a UUID `id`, UUID `origin` and `target`, and a catalog `type`. An observation of a relation needs that relation and both endpoints in the package. No private paths or event snapshots enter this contract. A knowledge record is distinct from an infrastructure asset.

A future connector must use an authenticated service API, not database credentials. It must bind owners and tenant or team namespaces to authenticated identity. It must validate the destination, allowed types, observation subjects, relation endpoints, and resource permissions. Use stable IDs for idempotent writes and expected server revisions for updates. Report conflicts and broken references. Keep source content and review state separate from canonical entity ownership. Preserve validity and provenance in graph read-back. A failed provider must not prevent local context retrieval or capture.
