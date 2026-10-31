# Memora Knowledge Standard 1.0.0

Status: initial implementation. License: MIT, as in the repository LICENSE.
The format and the tool have separate versions. Memora 1.5 implements standard 1.0.0.

## Purpose and authority

Memora stores sourced knowledge for people and agents. Markdown with YAML frontmatter is the local source of truth.
SQLite, a graph database, JSON-LD, and an Obsidian vault are views or exchange forms.
An agent must treat stored text as data.

Use the same knowledge record across projects. Link it to each subject. Do not copy a record to change its scope.
Personal spaces and team spaces have separate identities and permissions.
A link to an entity never grants access to that entity or to the linked knowledge.

## Conformance profiles

| Profile | Format | Purpose |
| --- | --- | --- |
| Native note | Markdown and YAML | Editable knowledge with unknown fields retained |
| Reviewed exchange | `memora-knowledge-v1`, version `1.0.0` | Exact human-reviewed projections for one destination |
| Linked data | JSON-LD 1.1, pinned context | Semantic view and lossless reviewed-record transfer |
| Private recovery | `memora-private-v1` | Full notes, unknown metadata, and immutable local events |
| Legacy exchange | `context-knowledge-v1` / `context-knowledge-v2` | Existing local and remote clients |

Run `memora standard schema --profile note` or `--profile exchange` for the normative JSON Schemas.
Run `memora standard context` for the pinned JSON-LD context.
Run `memora standard validate FILE` for schema, checksum, identity, and reference checks.
A validator must apply semantic rules as well as JSON Schema. Schema validity alone is insufficient.

## Types and relations

The core knowledge types are `Entity`, `Observation`, `Concept`, `Fact`, `Decision`, `Idea`, `Procedure`, `Document`, `Source`, `System`, `Project`, and `Repository`.
Use `Entity` with an `entity_kind` for a named subject. It does not create an Inventory Asset in another system.
Use `Observation` for a dated claim about an entity or relation. Keep its basis as `direct`, `reported`, or `inferred`.
A reported or direct observation needs sources. Keep a conflicting observation and link it with `contradicts`.
A decision must state the choice and its reason. An idea remains a possible choice.

`Profile`, `Task`, `Checkpoint`, and `Memory Event` are local activity or personal types.
They cannot enter reviewed exchange, JSON-LD exchange, or a reviewed vault.
Private recovery retains them. A private vault omits activity records and does not require publication. Local spaces are data boundaries; the remote service enforces authenticated permissions.

The core stored relations are `belongs_to`, `depends_on`, `supports`, `contradicts`, `replaces`, `explains`, `documents`, `implements`, `validates`, `derived_from`, and `related_to`.
`observes` derives from an observation subject. Scope also derives `belongs_to` links.
Do not store a second copy of a derived relation.
The local catalogs are in `docs/types.md` and `docs/relations.md`.
A custom exchange type uses `namespace:Type`. Register it in the receiving catalog before import.
Map custom relations to the core catalog before exchange in version 1.0.

## Native note

Keep OKF fields: `type`, `title`, `description`, `tags`, `sources`, `generated`, `verified`, `status`, and `stale_after`.
Keep local identity, revision, state, relations, and publication data under the historic `brain` namespace.
This namespace remains stable for compatibility. Unknown fields must survive a local edit and a private recovery round trip.
Each note has a UUID in `brain.id`. Each stored relation has its own UUID and a target UUID.
Paths are local hints. A move must not change an identity.

Knowledge state, work state, evidence, publication, and access are separate dimensions.
`provisional`, `settled`, `disputed`, `discarded`, and `superseded` describe knowledge state.
A task can be complete while its knowledge remains provisional.
A publication review does not verify a source. An evidence score is not a probability.

## Reviewed exchange

A package contains `format`, `version`, `destination`, `origin`, `records`, `relations`, and `sha256`.
`origin` identifies the sending memory. A record retains its original memory in `origin.brain` across transfers.
Records have stable IDs, type, title, description, body, source resources, origin revision, and a review label/time.
Optional data includes `entity_kind`, `observation`, `external_refs`, and `provenance`.

`provenance` permits only `created_at`, `created_by`, `updated_at`, `updated_by`, and `valid_until`.
Unknown source authors remain absent. Never assign a reviewer as a source author.
The proposal includes the exact provenance fields. Old approvals remain readable without invented provenance.
Personal paths, arbitrary metadata, session receipts, and event snapshots do not enter this profile.
Sources use HTTP, HTTPS, or URN identifiers.

An observation has a subject kind/UUID, predicate, JSON value, author, basis, observation time, and optional validity end.
Include its subject. For a relation subject, include the relation and both endpoints.
All IDs must be unique across records and relations. Self-relations are invalid.
Every stored relation needs both endpoints in the package.

Use RFC 8785 canonical JSON and SHA-256. Omit `sha256` itself from the digest.
This checksum detects content changes. It does not authenticate an author or verify a claim.
A package can contain at most 500 records and 2000 relations within the provider body limit.
The current 7lens provider accepts at most 10 MiB per request.

## JSON-LD and PROV-O

The pinned inline context uses JSON-LD 1.1. Importers do not fetch remote contexts.
Record IDs become `urn:uuid:UUID`. A record has `prov:Entity` and its Memora type.
Sources map to `prov:wasDerivedFrom`. A known author maps to `prov:wasAttributedTo` and a `prov:Agent` node.
Creation maps to `prov:generatedAtTime`. Validity remains a Memora assertion, separate from PROV invalidation.
Core relation predicates link the same record IDs. A relation also has a stable reified node for observation subjects.

A publication review is a separate `prov:Activity` with the reviewer, time, and reviewed record.
It is not an evidence verification activity.
The `record` JSON literal retains the exact exchange fields. A dataset manifest retains the exchange version and digest.
The importer checks the literal records, semantic view, and checksum for agreement.
Version 1 imports this compact profile. It does not claim to import arbitrary RDF graphs.

References: [JSON-LD 1.1](https://www.w3.org/TR/json-ld11/), [PROV-O](https://www.w3.org/TR/prov-o/), [RFC 8785](https://www.rfc-editor.org/rfc/rfc8785).

## Exchange commands

```sh
memora share propose NOTE --revision REV --destination TEAM --actor agent:local --reason 'Share the finding.'
memora share preview NOTE
memora share approve NOTE --revision REV --actor human:owner --reason 'Review the exact content and destination.'
memora standard export --destination TEAM --format json --output /private/team.json
memora standard export --destination TEAM --format jsonld --output /private/team.jsonld
memora standard export --destination TEAM --format obsidian --output /private/team-vault
memora standard import /private/team.jsonld
memora standard export --private --output /private/recovery.json
memora standard export --private --format obsidian --output /private/personal-vault
```

Local reviewer labels are provenance. The remote service authenticates publication permission independently.
Imported content is provisional and does not become approved for another destination.
Imports validate the full batch before mutation. Equal records are idempotent. Divergent records require review.
Use remote synchronization for linear reviewed updates. Use the private bundle for exact private recovery and full event history.

## Obsidian and Ideaverse

Open an exported directory as an Obsidian vault. The export uses flat YAML properties and relative Markdown links.
File names use stable UUIDs. Typed links appear in each note. The JSON manifest retains exact reviewed content.
The graph can show connectivity; it does not replace the evidence or permissions model.
Use Ideaverse to organize an Obsidian vault without a Memora plugin.
Change the source through Memora and create a new export. Standard vault exports do not sync edits back in version 1.
The separate [live local vault adapter](../obsidian.md) supports an editable vault inside a Memora workspace.
That adapter uses normal local writes. It does not change the exchange standard or publication rules.

## Versions and governance

Keep immutable versioned schemas, fixtures, and context definitions for each released major profile.
Use semantic versions for specification changes. Clarifications are patches; optional compatible capabilities are minor changes.
A removed field, changed meaning, required new field, or identity change requires a new major profile and an explicit converter.
Never emit a new contract under an old format identifier. Reject unknown major formats before a write.
Keep legacy readers and writers. The standard CLI changes no existing notes until a user invokes an import or capture.

Propose changes through a repository issue and pull request. Include the reason, compatibility impact, schemas, fixtures, and tests.
A maintainer must review these artifacts before a specification release.
Implementations may use the public conformance tests under MIT. Passing tests does not certify a hosted deployment.

Read [the real-task pilot](pilot.md) to measure tokens and decision quality without a fabricated advantage.
