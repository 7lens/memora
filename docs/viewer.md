# Local knowledge explorer

Run `memora view` to open the local interface. It uses the same Markdown store and revision rules
as the CLI. It binds to `127.0.0.1` and needs no MCP process, model service, or internet connection.
Press `Ctrl+C` in the terminal to stop the server.

```sh
memora view
memora --workspace team view
memora view --no-open
```

The page opens with a light theme. Use the theme button in the header for a dark theme. The browser
retains the choice for that local address. A new server port can have a separate browser preference.
The interface uses compact panels, a navigation rail, a graph canvas, and a note inspector.

## Find context

The overview shows actual note, connection, source and review counts. The counts describe the
selected local space. They do not certify evidence quality. Quick views select all knowledge,
notes that need review, stale sources, agent inferences, or content approved for sharing.

Combine those views with search, project, repository, type, state and minimum score. Search also
checks tags and source references. Filter chips remove one condition; Reset filters removes all
conditions. Press `/` outside a form to focus search. Mobile uses a quick-view menu in place of
the navigation sidebar.

The graph starts with clusters for projects, repositories and shared context. Shared means across
projects in the local space; it does not publish content. Open a cluster to inspect its notes.
Select Expand to show all matching notes. Drag to pan and use the wheel or zoom buttons to zoom.
Fit graph centers the visible items. Hover a node to read its name. Node colors stay stable when
new types enter the graph. Cluster names remain visible on small screens.

Use List for keyboard access, sorting and pages of 50 notes. The canvas shows at most 500 nodes
and 2,000 relations. The status line reports omitted items. Source Markdown remains authoritative;
canvas positions and visible edges are projections.

## Read and change knowledge

Select a note to read its full Markdown content. The server disables raw HTML and unsafe link
protocols. The inspector separates Content, Evidence, Relations and History. Use the arrow keys
within its tab bar. Previous note and Next note return to notes in the current navigation history.
The Relations tab follows directed links, adds typed relations and opens a neighborhood view.

Add knowledge captures a subject, concept, fact, decision or procedure. Record observation keeps
a dated claim about a subject or relation. Evidence shows source references, basis and validity.
It identifies an inference explicitly. Publication review does not verify a claim.

Edit note changes title and content with the current revision. It preserves identity, unknown
metadata, source references and immutable history. A concurrent write returns a revision conflict
and keeps the form content. Live refresh also keeps an open form. Cancel the form to load the
current note before a new edit. A changed approved note needs a new sharing review.

Propose or review sharing shows the exact projection and destination. Approval requires a human
action. Export reviewed knowledge downloads the approved projection. Profiles, checkpoints and
private event history do not enter that projection.

The workspace selector reloads the page for the selected space. Named CLI views keep the shared
root and start with the requested space. Local spaces provide data boundaries, not multiuser
permissions. Use an authenticated connected backend for remote access control.

## Checks

Run `PYTHONPATH=src .venv/bin/pytest -q` for storage, rendering, revision and access checks. Run
`PYTHONPATH=src .venv/bin/python scripts/browser_test.py` for Chromium workflows. Browser fixtures
use temporary notes. They cover desktop and mobile layouts, dark theme retention, safe Markdown,
keyboard tabs, concurrent editing, live form retention, sharing invalidation and the 10,000-note
canvas limit. Review the generated screenshots before delivery.
