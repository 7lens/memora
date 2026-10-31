# Portable remote profile

The service API is independent of a graph database. Use the authenticated service API, without database credentials.
7lens is the first implementation. The native 7lens model remains authoritative for its entities and ownership.

A local workspace maps to one authenticated server space.
Personal ownership comes from verified user identity. Each team has explicit reader, contributor, reviewer, and administrator memberships.
Global administration can manage a team without reading its content. It cannot read another person's private space.
A machine can propose content; publication requires an authenticated human reviewer.
A local `human:*` label is insufficient authorization.

The API prefix is `/v1/knowledge`. These operations form the provider contract:

| Route | Operation |
| --- | --- |
| `/spaces` | GET accessible spaces; POST a personal/team space |
| `/spaces/{space}/members` | PUT membership with expected revision |
| `/spaces/{space}/records` | GET published search with q, offset, limit |
| `/spaces/{space}/records/{id}` | GET authorized record |
| `/spaces/{space}/records/{id}/history` | GET authorized immutable revisions |
| `/spaces/{space}/records/{id}/references` | GET authorized external reference resolution |
| `/spaces/{space}/imports` | POST package, expected revisions, preview, publish |
| `/spaces/{space}/proposals` | POST a record and expected revision |
| `/spaces/{space}/records/{id}/review` | POST revision and published/withdrawn state |
| `/spaces/{space}/graph` | GET bounded published graph or record neighborhood |
| `/spaces/{space}/changes` | GET published changes and withdrawals after since cursor |
| `/spaces/{space}/export` | GET published package; format selects legacy v2 or MKS v1 |

Imports are atomic. Equal replays are idempotent. Transfers retain origin IDs.
A stale expected revision returns 409. Invalid references return 422. Unavailable spaces return 404.
An authenticated space member must pass permissions on every list, read, history, and reference request.
No unpublished draft body enters the reader change feed. An approved version remains readable while a reviewer checks an edit.
A withdrawal retains the previous published content and its audit trail. It does not expose the current draft.
Membership revocation prevents later reads; it cannot erase an authorized user's earlier local copy.

New remotes select `memora-knowledge-v1`. Existing remote configuration keeps legacy v2 unless explicitly replaced.
Use `--protocol context-knowledge-v2` for an older provider. Legacy v2 omits the new provenance block.
MKS transfers provenance and the exact reviewed source records. A provider outage leaves local capture and retrieval available.

```sh
memora remote add team --url https://api.example.org --space SPACE_UUID --domain https://identity.example.org --client-id PUBLIC_CLIENT --scope customer/access
memora remote login team
memora remote push team --preview
memora remote push team
memora remote pull team
```

Plain push proposes. The authenticated reviewer publishes through a review operation or an explicit `push --publish`.
Use expected revisions, cursor checks, and a recoverable local journal.
Keep both versions on conflict. Resolve with `remote resolve`; there is no silent last-write-wins policy.
A published record can become available again after withdrawal. Its local knowledge state returns to provisional.

A 7lens reference contains provider `7lens`, installation identity, entity_type, entity_id, relation, and optional observed_revision.
Resolve it against the caller's authorized canonical view. Never match by display name.
Unknown, deleted, unsupported, or unreadable entities return unavailable. Preserve the reference and last observed revision.
Reference resolution does not create entities, copy Inventory assets, or change canonical ownership.

The first 7lens store keeps state and immutable revisions in one managed graph transaction.
It supports Neo4j and Neptune graph sessions. Graph projections keep knowledge labels separate from configuration labels.
Large histories require partitioned storage and indexed search before scale rollout.
Live identity-provider and database deployment acceptance remains separate from hermetic protocol tests.

Imported validity sets the local expiry check. An expired source remains visible as stale context.
Use `memora remote references team --id RECORD_UUID` to resolve references through the authorized API.
