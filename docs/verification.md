# Verification record

## Local tests

The unit tests cover note round-trip, type definitions, graph relations, and scores. They cover history, concurrent changes, recovery, context scope, editor installation, checkpoint candidate retention, and health reports.

The current suite passed 154 tests on the installed Python version. The checkpoint test confirms that updates keep earlier memory candidates and ideas. The health test covers stale notes, provisional facts, low evidence scores, and missing targets.

The scale test uses 10,000 Markdown entities. A warm refresh reads no unchanged note files. The live viewer returns graph metadata for all 10,000 entities and limits the canvas to 500 nodes and 2,000 edges.

The Chromium browser test passed 71 checks. It covers graph guide content, cluster spacing, drag navigation, cluster expansion, filters, list-column overlap, safe text display, live refresh, desktop and mobile layouts, empty memory, and the 10,000-node limit.

## Context and connector checks

A real stdio MCP client completed initialization, tool discovery, context retrieval, note reading,
local capture, recall, and session status. Its status matched the local receipts. Error calls kept
the error result. The doctor probe checked a real connection without creating a task receipt.

Context tests include 300 unrelated PR sources and 260 foreign-scope matches. They check relevance,
source excerpts, revision snapshots, private note updates, and session scope. Private bundles
round-trip unknown fields, typed external references, and immutable events. Tests cover idempotent
imports, linear history advances, identity conflicts, corrupt input, interruption recovery, and
external changes during recovery.

The optional model passed 20 synthetic English and Spanish queries offline. Each expected concept
appeared in the first five results. The evaluation also checked cache invalidation after a note
change. The model revision was `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`. Run
`scripts/evaluate_memory.py --model-root <brain with downloaded model>` with the semantic extra.
This fixture result does not establish quality on every personal knowledge corpus.

The browser checks include session receipts and unchecked external graph nodes. The optional remote adapter now has separate API transfer checks.

## Language review

The language target is ASD-STE100 Issue 9. This machine has no complete standard or dictionary. Vocabulary coverage remains partial.

Automatic checks do not certify compliance. Use the official reference for a full language review.

## Editor sessions

The adapter tests use a temporary home directory. They confirm file preservation, Codex overrides, repeat installation, and removal.

A global pointer alone does not confirm access from an editor session. A real session must load context, save a note, and read it again.

A real Codex session loaded context, saved a test note, and read it again in a temporary memory. The session found an editable installation issue. The release uses a normal package installation. A second real Codex session passed context, capture, search, and show with the installed CLI. It needed no path workaround.

Real Kiro, Copilot, and Antigravity sessions remain untested. Their instruction file adapters pass the local tests. These results do not confirm access from those editors.


## Version 1.2 checks on 2026-10-16

The final source suite passed all 124 pytest tests. The package was installed for CLI and browser checks. Ruff checks and format checks passed. The public-tree check found no tracked private memory. Chromium passed 71 checks with no browser errors. The new browser checks cover subject capture, full note reading, observation capture, exact projection review, approval, mobile width, and workspace isolation. The graph fixture still contains 10,000 nodes.

`scripts/evaluate_context.py` modeled four anonymized task patterns: personal preferences, a previous runtime decision, an entity finding, and unfinished work from another chat. All four target notes appeared within the first three selected results. Packets used 649 to 1,334 bytes and stayed within the 12,000-byte limit. These small fixtures do not measure retrieval quality over every real corpus. No private corpus was exported for the evaluation.

The CLI path passed a subprocess check that rejects any MCP import. Base dependencies exclude MCP. The optional test extra includes MCP to check its separate transport. The local install uses version 1.2.0. Identity migration keeps a full backup before changes.

## Remote adapter verification

The 1.3 tests cover canonical JSON, reviewed export, PKCE state and challenge checks, private
credential files, incremental updates, withdrawals, staged failure and explicit conflict resolution.
The two-workspace CLI/API check recovered a decision in a new chat and read a later portal change.
Cross-language fixtures cover Unicode, escaping and numeric values. These checks use disposable
local state. They do not certify a live identity provider or a production graph deployment.

## Knowledge explorer checks

The 1.4 viewer checks cover safe Markdown, stable note identity, unknown metadata, immutable events, and stale edit rejection. The browser checks cover the portal layout, light and dark themes, keyboard tabs, automatic full note reading, form retention during refresh, concurrent writes, generic note capture and sharing invalidation. Fixtures use temporary memory and retain the 10,000-note canvas test. Screenshots cover desktop, mobile and dark theme layouts.

## Context study checks

The [context study](benchmark.md) has 11 tests for fixtures, source selection, scoring, failure
denominators, Codex tool rejection, token counts, command adapters, retained results, and blind
review pairs. These tests use temporary memory and stub responses. They do not call a model.

The separate retrieval check selects every expected source in the fixed 12-task fixture within
the 12,000-byte limit. It excludes the superseded owner record. This check does not measure agent
answer quality. The study stores actual model answers and runtime counts in public result files.
Only fictional context enters those runs.

The Codex pilot completed 48 calls. The repeated study completed 144 calls, with three repetitions
per task and condition. Both used `gpt-6-luna` with high reasoning effort. No execution error or
retry occurred. The [result review](../benchmarks/results/2026-10-16-codex-study/REVIEW.md) records
correct paraphrases and useful citations that the fixed rubric rejects. Automatic scores remain
unchanged. Human blind review remains pending.

The first full test attempt ran inside a sandbox that denied loopback sockets. Five HTTP tests
failed with `PermissionError`. The final run allowed temporary loopback servers and passed all
150 tests. No test assertions or HTTP checks were removed.

## Memora rename checks

The 1.4.1 source suite passed 154 tests after the package and CLI rename. Four new checks cover
the package name, CLI name, author metadata, existing version markers, private bundle formats,
and the `MEMORA_ROOT` variable. The installed viewer passed 71 Chromium checks with no browser
errors. Desktop and mobile screenshots show the Memora name. The fixture still has 10,000 nodes.

The local install uses `memora`. Editor instructions use `python -m memora` with the CLI transport.
The memory reader accepts existing notes and version history. No memory reconsolidation is required.
Original model study records retain their measured labels, prompts, responses, and checksums.
