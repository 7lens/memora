# Remote knowledge transfer

The optional remote adapter exchanges reviewed knowledge through an authenticated API. It does not
need a local MCP process. Local capture and context remain available when the provider fails.
Install the adapter with `pip install '.[remote]'` from this repository.

Select a local workspace before each command. A remote maps that local space to one authorized
server space. Create the server space in its portal first. Keep its UUID.

```sh
memora remote add customer --url https://graph.example.org --space SPACE_UUID \
  --domain https://identity.example.org --client-id PUBLIC_CLI_CLIENT --scope customer/access
memora remote login customer
memora remote status customer
```

The server must accept the CLI client and scope. Register the exact public-client callback
`http://127.0.0.1:8766/callback`, or use `--redirect-uri` with another registered loopback port.
Login uses PKCE, a one-use state, and a three-minute timeout. Tokens stay in private local files.
Refresh occurs on demand. Logout revokes the refresh token when possible, removes local tokens,
and stops transfer until the next login. Never put a client secret in a public CLI client.

For automation, use `--secret-file /private/client-secret` with `--domain`, `--client-id` and
`--scope`. A `--token-file /private/access-token` also works. Both files must have mode 600.
Machine identities need explicit server space membership and cannot approve publications. For
local development only, `--local` permits a loopback API with authentication disabled.

## Review and transfer

Propose and approve the exact content with the existing `memora share` commands. Use the server
space UUID as the destination. The projection excludes working memory, personal profiles and private history.

```sh
memora share propose NOTE_PATH --revision REV --destination SPACE_UUID \
  --actor agent:local --reason 'This context helps the team.'
memora share preview NOTE_PATH
memora share approve NOTE_PATH --revision REV --actor human:owner \
  --reason 'I reviewed the exact content and destination.'
memora remote push customer --preview
memora remote push customer
memora remote pull customer
memora remote logout customer
```

Push sends proposals by default. `push --publish` is an explicit server publication request; the
server must authenticate a human reviewer. Local review labels do not grant that permission.
A change to approved local content requires a new review. A replay is idempotent. Updates carry
the last server revision. Pull reads published changes and withdrawal markers. It keeps normal
local note events and marks withdrawn notes discarded. It does not erase their evidence.

A new local space can pull its first knowledge and start a task without a repository:

```sh
memora --workspace team remote pull customer
memora --workspace team start --task 'support policy and prior decisions'
```

Use `memora --workspace team remote add ...` first in that space. Each local workspace has its
own credentials, origins, cursors and transfer baselines. That metadata stays outside shared notes.

## Resolve a conflict

Concurrent local edits stop the pull. A private report keeps the incoming versions. Local notes
and the saved cursor remain intact. Select one version explicitly:

```sh
memora remote resolve customer --id NOTE_UUID --take remote
memora remote resolve customer --id NOTE_UUID --take local
```

Keeping a local version records the incoming revision as the next expected server revision.
Review the local projection again before push. A later server edit can still cause another conflict.
Taking a remote version uses the normal local note revision and keeps the previous event history.
A recoverable write journal covers downloaded notes, events and cursor advancement. Recovery
stops if an unrelated writer changed a journal target.

## Exchange version

Run `memora remote schema` to read the v2 JSON Schema.
The adapter writes `context-knowledge-v2`. It uses RFC 8785 JSON canonicalization and SHA-256.
The stable sending memory UUID and each record's origin identify content across transfers. A checksum
checks integrity; it does not authenticate a reviewer or verify a claim. The API enforces access.
The local `context-knowledge-v1` reader and export remain available. Convert a v1 file explicitly:

```sh
memora remote convert /private/v1.json --output /private/new-v2.json
```

Conversion checks the old checksum and assigns this memory as the transfer origin. It does not
publish content. The provider must support v2. Keep unknown local fields in Markdown; the reviewed
projection continues to exclude unknown private metadata.
