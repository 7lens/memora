# Connect a local agent

Memora stores personal and team context. The CLI is the default interface. A client must run
`memora start` before memory appears in its task context. An installed server is not proof of use.

## Install

From the Memora repository:

```sh
python3 -m venv .venv
.venv/bin/pip install .
.venv/bin/memora install --editor codex --dry-run
.venv/bin/memora install --editor codex
.venv/bin/memora doctor
```

Choose `codex`, `kiro`, `copilot`, `copilot-local`, or `antigravity`. `copilot` targets Copilot CLI.
`copilot-local` targets the VS Code user profile. Use `all` to install every supported adapter.
The installer preserves existing instructions and other server settings. Codex TOML comments stay
intact. JSON configuration files use strict JSON; resolve JSON comments before installation.

Restart the agent session. The default install starts no MCP process. The installer
sets no automatic tool approval policy. It uses the Python interpreter that ran the install
command. Keep that environment available. After you move it, reinstall the package and adapter.

`doctor --probe` starts a subprocess and makes a real MCP status call. It does not create a task
receipt. A failed connection produces an error and a nonzero exit status.

## Optional MCP configuration

Install the optional dependency with `.venv/bin/pip install '.[mcp]'`. Run
`memora install --editor codex --transport mcp` to select MCP explicitly. Use `memora doctor --probe`
only for that transport. Installing again with `--transport cli` removes only an unchanged managed
MCP entry. Other servers and client settings remain intact.

## Common MCP configuration

The process command is the absolute path to `.venv/bin/python`. Arguments are:

```json
{
  "mcpServers": {
    "memora": {
      "command": "/absolute/path/memora/.venv/bin/python",
      "args": ["-m", "memora", "--root", "/absolute/path/memora", "mcp"]
    }
  }
}
```

Use `mcp_servers` in Codex TOML. VS Code user profiles use `servers` and `type: "stdio"`.
Copilot CLI uses `type: "local"` and `tools: ["*"]` in its server entry. These entries expose
available tools; they do not bypass client approval controls. Standard output contains only MCP
messages. Diagnostics use standard error.

The managed steering block requires the agent to run `memora start --task` and show the receipt.
Add `--cwd` for code work. The optional MCP mode uses `start_task` with the same service. It also requires a new query when the task changes and local knowledge capture
when the agent learns something useful. Steering is an instruction, not an execution hook.
Client behaviour can differ. Inspect receipts instead of assuming that the instruction ran.

## First conversation

Ask your agent to recall project decisions before a task. It must:

1. Run `memora start --task '<English task terms>'`. Add `--cwd` for code work or select a project or entity.
2. Show the receipt message and use the returned excerpts and sources.
3. Run `memora show NOTE_PATH --session SESSION_ID` for full content and a recorded read.
4. Run `memora recall --session SESSION_ID --task '<new terms>'` when the task changes.
5. Run `memora remember` for useful concepts, sourced findings, procedures, and decisions with reasons.
6. Use `memora observe` for dated findings. Propose useful sharing candidates; ask a human to review the exact projection before approval.

A task with `--cwd` registers the local repository if it is not known. A general task needs no repository. Existing project associations
remain in use. A scoped task can include a directly related project. Similar words alone do not expand its scope.
Facts need sources. Unsourced claims belong in Idea notes. New notes remain provisional.
For an existing subject, `remember` returns the note path and revision. Read it before an update.
Unknown metadata and typed relations remain intact. Wrong revisions fail without changing the note.
Checkpoints remain task progress; their candidates do not become confirmed knowledge automatically.

The agent extracts knowledge. Memora has no background conversation recorder or inference
service. It does not store complete chats. It cannot prove that a model understood its output.

CLI users can use the same service:

```sh
memora start --cwd /absolute/path/project --task 'platform membership rules'
memora recall --session SESSION_ID --task 'asset ownership'
brain status --session SESSION_ID
memora view
```

## What the feedback means

| State | Evidence |
| --- | --- |
| Configured | Instructions and a server entry exist. |
| Connection verified | A real local MCP initialization and status call passed. |
| Context returned | A tool returned a context packet and recorded its selected notes. |
| Note returned | The service recorded a full note read for a session. |
| Knowledge saved | A local note change completed with a revision and immutable event. |

No state means that the model applied the memory correctly. Inspect `brain status` or the Session
receipts section in the live viewer. Receipts list selected notes, types, bytes, source checks, and
search mode. They omit the raw task prompt. Empty context is distinct from an access failure.
A current session needs its own receipt; old receipts are history, not proof of a new call.

## Optional search by meaning

```sh
.venv/bin/pip install '.[semantic]'
.venv/bin/memora semantic enable
.venv/bin/memora semantic status
```

Enable downloads the model and records its exact commit hash. This command does not send notes
outside the machine. Later queries load local files only. The model is
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`. It supports multilingual retrieval.
The local cache contains vectors, source hashes, and the model revision. Note changes invalidate
cached vectors. Removing the cache does not remove knowledge.

Without the extra or model files, text and graph search still work. A receipt reports an unavailable
semantic engine and its error. It never claims hybrid search when only text search ran.
`memora semantic disable` stops model use and keeps the downloaded files. First model load and first
index build can take longer than later queries. Context remains bounded to 12,000 bytes by default.
The packet contains at most eight knowledge notes, plus scope anchors. Full content is available separately.
The budget covers the text packet; structured receipt metadata is additional.

## Client references

- [Codex MCP](https://developers.openai.com/codex/mcp)
- [Kiro MCP configuration](https://kiro.dev/docs/mcp/configuration/)
- [VS Code MCP](https://code.visualstudio.com/docs/agent-customization/mcp-servers)
- [Copilot CLI MCP](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-mcp-servers)
- [Antigravity MCP](https://antigravity.google/docs/mcp)
