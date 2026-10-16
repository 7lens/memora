"""Test the live viewer with a temporary memory."""

import argparse
import json
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

from memora.index import Index
from memora.live import make_server
from memora.store import Store
from memora.service import MemoryService
from memora.viewer import data as viewer_data, render_data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--chrome",
        default="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or Path(tempfile.mkdtemp(prefix="memora-browser-"))
    output.mkdir(parents=True, exist_ok=True)
    root = output / "fixture"
    root.mkdir(exist_ok=True)
    project_root = Path(__file__).resolve().parents[1]
    shutil.copytree(project_root / "docs", root / "docs", dirs_exist_ok=True)
    store = Store(root)
    from memora.knowledge import workspace_create

    workspace_create(store, "team", "team")
    project = store.create(
        {
            "type": "Project",
            "title": "Example project",
            "description": "A graph test project.",
        },
        "",
        "process:test",
        "Add the fixture project.",
    )
    repo = store.create(
        {
            "type": "Repository",
            "title": "Example source",
            "description": "A test source repository.",
            "brain": {"projects": [project["path"]]},
        },
        "",
        "process:test",
        "Add the source repository.",
    )
    first = None
    for kind in [
        "Idea",
        "Concept",
        "Fact",
        "Decision",
        "Task",
        "Procedure",
        "Document",
        "System",
        "Source",
    ]:
        data = {
            "type": kind,
            "title": "Cache " + kind,
            "description": "A source concept for the cache.",
            "tags": ["software"],
            "brain": {"projects": [project["path"]], "repositories": [repo["path"]]},
        }
        if first:
            data["brain"]["relations"] = [{"type": "supports", "target": first}]
        note = store.create(
            data, "Use the source document.", "process:test", "Add the fixture note."
        )
        first = first or note["path"]
    store.create(
        {
            "type": "Idea",
            "title": "</script><script>window.INJECTED=true</script>",
            "description": "A safe display test.",
            "tags": ["security"],
            "sources": [{"resource": "javascript:window.INJECTED=true"}],
            "brain": {"state": "settled"},
        },
        "",
        "process:test",
        "Inspect safe display.",
    )
    service = MemoryService(store)
    session = service.context("cache", root.resolve(), repository=repo["path"])
    service.get_note(first, session["receipt"]["session_id"])
    index = Index(store)
    index.refresh()
    text = render_data(viewer_data(index))
    (output / "memora.html").write_text(text)
    start = text.index('<script id="memora-data" type="application/json">') + len(
        '<script id="memora-data" type="application/json">'
    )
    end = text.index("</script>", start)
    payload = json.loads(text[start:end])
    sample = payload["nodes"][2]
    payload["nodes"] = [
        dict(
            sample,
            path=f"/nodes/large-{i}.md",
            title=f"Large node {i}",
            score=(i % 4 + 1) * 25,
        )
        for i in range(10000)
    ]
    payload["edges"] = [
        {
            "origin": f"/nodes/large-{i}.md",
            "target": f"/nodes/large-{i - 1}.md",
            "kind": "related_to",
        }
        for i in range(1, 10000)
    ]
    payload["events"] = []
    encoded = json.dumps(payload).replace("<", "\\u003c").replace(">", "\\u003e")
    (output / "large.html").write_text(text[:start] + encoded + text[end:])
    empty_root = output / "empty"
    empty_root.mkdir(exist_ok=True)
    empty = Index(Store(empty_root))
    empty.refresh()
    (output / "empty.html").write_text(render_data(viewer_data(empty)))
    empty.close()
    index.close()
    external_root = output / "external"
    external_root.mkdir(exist_ok=True)
    shutil.copytree(project_root / "docs", external_root / "docs", dirs_exist_ok=True)
    external_store = Store(external_root)
    external_store.create(
        {
            "type": "Concept",
            "title": "Platform guidance",
            "brain": {
                "external_refs": [
                    {
                        "provider": "external-graph",
                        "instance": "demo",
                        "entity_type": "platform",
                        "entity_id": "payments",
                        "relation": "documents",
                        "observed_revision": "4",
                    }
                ]
            },
        },
        "Link a platform to its service definitions.",
        "process:browser-test",
        "Check external display.",
    )
    external_index = Index(external_store)
    external_index.refresh()
    (output / "external.html").write_text(render_data(viewer_data(external_index)))
    external_index.close()
    live_requested = threading.Event()
    server = make_server(root, on_api_request=live_requested.set)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    def add_live_note():
        Store(root).create(
            {"type": "Fact", "title": "Live change detected"},
            "The page reads new Markdown from this repository.",
            "process:browser-test",
            "Check live refresh.",
        )

    def update_after_live_request():
        if live_requested.wait(timeout=15):
            add_live_note()

    update_thread = threading.Thread(target=update_after_live_request, daemon=True)
    update_thread.start()
    try:
        result = subprocess.run(
            [
                "node",
                str(project_root / "scripts/browser_test.mjs"),
                args.chrome,
                str(output),
                f"http://127.0.0.1:{server.server_port}/",
            ],
            check=False,
        )
    finally:
        update_thread.join(timeout=1)
        server.shutdown()
        server_thread.join(timeout=2)
        server.server_close()
    print("Browser artifacts:", output)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
