# Memora

Durable context and shared knowledge for agents. Public repository: [7lens/memora](https://github.com/7lens/memora).

Memora stores shared knowledge for agents. Markdown files contain the full memory. A local index makes searches fast.

Use ASD-STE100, Issue 9, for all text that you add. Keep code and source quotations unchanged.

## Install

Use Python 3.11 or later. Run these commands from this repository:

```sh
python3 -m venv .venv
.venv/bin/pip install '.[test]'
.venv/bin/memora install --dry-run
.venv/bin/memora install
```

The install command adds CLI instructions to each editor. It starts no server. It supports Codex, Kiro, Copilot, and Antigravity. It keeps existing instructions. Restart an agent session after installation.

Use the full path to `.venv/bin/memora` if `memora` is not on PATH. You can set `MEMORA_ROOT` or supply `--root` before a command.

## Start with useful context

Read the [local integration guide](docs/local-integration.md) for installation, first use, receipts,
and optional local search. Use `memora install --editor <editor>` to select one client. Run
`memora doctor` to check the installation. Restart the agent session.

The agent must run `memora start` and show its receipt. The context contains relevant note excerpts,
sources, selection reasons, and a bounded list of omitted notes. Scope anchors do not pull every
linked issue into a task. `memora recall` refreshes context; `memora show` reads full content; `memora remember` saves
useful local knowledge through the same write service as the CLI.

The live viewer includes session receipts and external graph references. Installation and a
connection are distinct from a context call. A receipt does not prove model understanding.

Optional local semantic search combines meaning, text, and graph context. Install `.[semantic]`,
then run `memora semantic enable` to download and pin the model. Queries use local files only.
The base installation needs no model or external inference service.

[Private bundles and future connectors](docs/private-sync-contract.md) describe portable memory
and generic external references. Reviewed projections can move between local team spaces. Remote synchronization is a separate connector.

## Keep personal memory local

The `knowledge/` directory stores local memory. Git ignores the full directory on every branch. The CLI checks this rule before it writes memory. Do not force-add memory files to Git. A Git ignore rule does not protect local files from other software on the same machine.

Shared scope means across projects in one user's personal memory. It does not grant access to other users.

The public repository does not track memory data. CI checks that no path under `knowledge/` is tracked.

## Version memory

The tool uses semantic versions. Version `1.1.0` and other `1.x` releases do not require memory reconsolidation. A major release such as `2.0.0` can require it.

After a pull, update the local CLI with `.venv/bin/pip install --no-deps .`, then run `memora version`. If `memora context` reports an old or unknown memory version, read each required major release procedure in `CHANGELOG.md`. Complete the steps, run `memora validate`, and then run `memora reconcile --reason '<summary of the review>'`.

The local marker is `knowledge/.memora-version.json`. It records the latest tool version that passed reconciliation. Git ignores it with the rest of `knowledge/`.

## Add a project

```sh
memora register project --name 'Example' --description 'A project for a local tool.'
memora register repository --name 'Example API' --cwd /path/to/repo --project /projects/example-ID.md
```

Use the path from the first command in the second command. Repository paths stay in local machine configuration. Register repositories under `repositories/`.

## Save knowledge

```sh
memora capture --type Idea --title 'Use a shared cache' \
  --description 'A shared cache can reduce repeated reads.' \
  --body 'Do a speed check before the change.' \
  --tag performance --scope shared \
  --actor codex/unknown --reason 'Keep the idea for a later review.'
memora search 'shared cache'
memora context --query 'shared cache' --cwd /path/to/repo
memora show /nodes/use-a-shared-cache-ID.md
```

Use English search terms. The agent must convert the task to clear search terms when needed.

Updates need the current revision. The CLI returns the new revision after a write.

Use `--tag` to classify the subject. Use `--project` or `--repository` to set scope. Use `--scope shared` when a note applies across projects. The default scope is pending. `memora validate` reports missing tags and scope. Project and repository scopes also create graph edges.

When you pass `--metadata`, the CLI keeps existing tags, sources, relations, scope, and unknown fields. New command-line values add to the metadata values. `--code-cwd` needs a registered repository. It records the Git revision and branch and links the note to that repository.

```sh
memora transition /nodes/NOTE.md --revision 1 --state settled \
  --actor codex/unknown --reason 'The design review supports this choice.'
memora verify /nodes/NOTE.md --revision 2 --evidence /path/to/result.txt \
  --actor process:source-check --reason 'The result confirms the current note.'
memora history /nodes/NOTE.md
memora history /nodes/NOTE.md --at 2026-10-06T12:00:00Z
```

## Keep session notes and long-term knowledge

Use a checkpoint as working memory for a task. Add durable facts as candidates and add future work as ideas:

```sh
memora checkpoint --session task-123 --repository /nodes/REPOSITORY.md \
  --goal 'Compare two memory tools.' --progress 'Read both designs.' \
  --next 'Add compatible features.' --candidate 'The current index uses SQLite FTS5.' \
  --idea 'Compare semantic search options.' --reason 'Record task progress.'
```

Add `--revision` when you update the checkpoint. Add more `--candidate` or `--idea` values as needed. The CLI keeps earlier values. Review each candidate before you add it to a long-term note. Use `memora capture` or `memora update` for that note. These writes keep the normal revision check and immutable event. Mark the checkpoint done with `memora transition` after you finish the task. A checkpoint does not make its candidates confirmed facts.

Use `human:<id>` only for an explicit human action. Do not invent a user confirmation. A source check needs an evidence file.

## Inspect the memory

```sh
memora validate
memora health
memora language check README.md
memora doctor
memora view
```

`memora view` opens a local knowledge explorer with light and dark themes, quick views, a graph and a note inspector. It reads full content on selection and supports capture, revision-checked editing, relations and publication review. Live refresh retains open forms. Read the [viewer guide](docs/viewer.md) for navigation, keyboard access and local space selection.

The live graph and list use the same filters for projects, repositories, types, knowledge states, and evidence scores. Search also checks tags and source names. The list sorts by each column and shows 50 notes per page. The graph groups notes by project or repository. Notes without a project or repository appear in the shared group.

## Open knowledge standard

Read [Memora Knowledge Standard 1.0.0](docs/standard/README.md) for the public format, node catalog,
JSON-LD/PROV-O mapping, conformance rules, and compatibility policy.
Use `memora standard export --destination TEAM --format obsidian --output /private/vault`
to create an Obsidian vault without a plugin.
The [capture guide](docs/standard/ingestion.md) defines private batch ingestion from agent conclusions.
The [remote profile](docs/standard/remote.md) defines authenticated team synchronization with 7lens.

## Use Obsidian as a local editor

Run `memora obsidian start` to create and monitor a private `obsidian/` vault inside this project.
Open that directory as a vault in Obsidian. New memory appears automatically while the process runs.
Edits and new notes in `Notes/` use normal Memora writes, revisions, and history.
Git ignores the vault. Edits do not approve team publication or verify evidence.
Run `memora obsidian status` for pending conflicts and `memora obsidian stop` to stop synchronization.
Start the process again after a computer restart. Read the [live vault guide](docs/obsidian.md) for editing and conflict resolution.

## Knowledge format

`knowledge/` is an OKF 0.2 bundle. Each note has YAML frontmatter. Each change has an immutable event. `index.md` and `log.md` support navigation.

`docs/types.md` defines the entity types. Add a type definition before its first use. `docs/relations.md` defines relation types. Add a relation definition before its first use. `docs/glossary.md` defines technical terms.

Use `brain.relations` for typed relations. The CLI writes the same relations as Markdown links. An error in either form must receive a correction. An unresolved target remains in the graph.

Use a source link for a large technical document. Save its summary as a `Document` note. Keep ideas, facts, decisions, and documents as separate notes when their review needs differ.

`memora health` lists expired notes, provisional facts, low evidence scores, open contradictions, and relations with missing targets. These items need review. The report does not confirm a fact or decide how to resolve an item.

## Evidence score

| Score | Evidence |
| --- | --- |
| 25 | Agent inference without a concrete source |
| 50 | Concrete source recorded |
| 75 | Current content confirmed against a source |
| 90 | Explicit user confirmation |
| 100 | User confirmation and an independent check |

The score is an evidence signal. It is not a probability. An expired note has a maximum score of 50. An open contradiction has a maximum score of 25.

A state change does not increase the score. A content change invalidates its previous checks. A changed local evidence file also invalidates its check.

Knowledge states and work states are separate. A completed task can still contain valid knowledge.

## Local state

`.brain/` contains the search index, installation records, local paths, and a recovery journal. Git does not track this directory. The index can be rebuilt.

```sh
memora reindex
```

Do not remove a pending transaction. `memora doctor` completes recovery when the current content permits it. A conflicting external edit stops recovery.

The memory uses a kernel file lock. Process exit releases ownership automatically, including a forced termination.
The file `.brain/write.lock` remains on disk; its presence does not mean that memory is busy.
Never delete or replace that file while Memora runs. `memora doctor --clear-dead-lock` remains a compatible recovery command; it does not remove the file.
Stop old long-running clients before an update. Read the [locking guide](docs/locking.md) for migration and diagnostics.

Use explicit Git commands to save and share the repository. The CLI does not make commits or push changes.

## Language checks

The checks use the ASD-STE100 Issue 9 language target. They report word length, selected vocabulary issues, and possible grammar issues. They do not certify compliance.

Supply `--standard /path/to/standard.pdf` and `--dictionary /path/to/dictionary.json` when these references are available. The dictionary format is in `docs/language.md`. Keep local reference paths in `.brain/config.json`.

The official standard and its dictionary remain the primary references. A language review must also inspect word meaning and part of speech.

## Tests

```sh
.venv/bin/pytest
.venv/bin/python scripts/browser_test.py
```

The browser test uses Chrome and Node.js. It runs a browser session with temporary data. It does not change the shared memory.

Read [the knowledge guide](docs/knowledge.md) for entities, observations, spaces, migration, and reviewed exchange.

See `docs/verification.md` for editor session results and known limits.

## Does stored context help?

The [context study](docs/benchmark.md) compares fresh Codex sessions under four conditions:
no stored context, all notes as plain text, Memora retrieval, and ideal note selection.
It uses 20 fictional notes and 12 tasks. These include technical and business context, task
continuation, contradictions, expired sources, missing facts, and a task that needs no memory.

The study measures answer accuracy, source support, incorrect answers, clarification questions,
context bytes, tokens, and time. It keeps the raw answers and failures. A receipt alone is not
evidence of a correct answer.

### First measured results

This study predates the project rename. Its original records retain their historical names and hashes.
Read the [name and compatibility guide](docs/rename.md) for the retained data contracts.

On 2026-10-16, the study ran 144 fresh Codex sessions: 12 tasks × 4 conditions × 3 repetitions.
The requested model was `gpt-6-luna` with high reasoning effort. No execution errors occurred.

| Context | Literal answer accuracy | Mean context bytes | Mean input tokens |
| --- | ---: | ---: | ---: |
| No stored context | 27.8% | 0 | 10,465 |
| All notes as plain text | 100.0% | 4,833 | 11,640 |
| Memora retrieval | 98.1% | 2,507 | 11,009 |
| Ideal note selection | 96.3% | 252 | 10,519 |

The fixed string rubric rejects three correct paraphrases: one with Memora and two with
ideal selection. An agent review found no difference in answer correctness among the conditions
with context. This was not a blind human review. The original scores remain in the
[results](benchmarks/results/2026-10-16-codex-study/RESULTS.md). Read the
[review](benchmarks/results/2026-10-16-codex-study/REVIEW.md) with the table.

Memora used **48.1% fewer context bytes and 5.4% fewer input tokens** than full notes.
Mean time rounded to 4.5 seconds in both conditions. The study does not establish a time saving
or better answer quality than full notes. Without context, Codex abstained from missing project
facts; it did not invent answers. The arithmetic control passed in all conditions.

These short synthetic tasks show context recovery with less input. They do not measure autonomous
CLI use, memory capture cost, real code changes, or user productivity. A separate
[48-call pilot](benchmarks/results/2026-10-16-codex-pilot/RESULTS.md) retains the initial results.

### Reproduce the study

Run a local retrieval check without a model:

```sh
PYTHONPATH=src .venv/bin/python scripts/benchmark_agent.py \
  --backend retrieval --repeats 1 --output exports/study-retrieval
```

Use the [study guide](docs/benchmark.md) to run the same tasks with Codex or another agent.
The guide defines each measure, comparison condition, and limit. Short context questions do
not establish developer productivity or money saved.

## Optional remote connection

Install `.[remote]` to use authenticated `memora remote` commands. Push reviewed projections,
pull published changes, and resolve conflicts explicitly. The CLI does not start a local MCP
server. See [remote knowledge transfer](docs/remote.md) for login, credentials and recovery.
