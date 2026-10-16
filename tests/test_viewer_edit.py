"""The local inspector uses canonical revisions and safe Markdown projections."""

import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from memora.live import make_server


def test_viewer_edit_retains_identity_metadata_and_events(store):
    original = store.create(
        {
            "type": "Decision",
            "title": "Support policy",
            "description": "A support decision.",
            "sources": [{"resource": "https://example.org/support"}],
            "custom": {"keep": "yes"},
        },
        "Use the current source.",
        "agent:test",
        "Keep the decision.",
    )
    metadata, _ = store.read(original["path"])
    identity = metadata["brain"]["id"]
    server = make_server(store.root)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(base + "/api/data") as response:
            token = json.load(response)["capability"]

        def post(body):
            with urlopen(
                Request(
                    base + "/api/action",
                    json.dumps(body).encode(),
                    headers={
                        "Content-Type": "application/json",
                        "Origin": base,
                        "X-Brain-Token": token,
                    },
                )
            ) as response:
                return json.load(response)

        change = {
            "action": "edit",
            "key": original["path"],
            "revision": 1,
            "title": "Updated support policy",
            "body": "## Support\n\nUse **approved** evidence.\n\n<script>window.UNSAFE=1</script>\n[bad](javascript:alert(1))",
            "reason": "Update the source summary.",
        }
        assert post(change)["revision"] == 2
        after, _ = store.read(original["path"])
        assert after["brain"]["id"] == identity
        assert after["custom"] == {"keep": "yes"}
        assert after["sources"] == metadata["sources"]
        assert len(store.events(original["path"])) == 2
        with urlopen(base + "/api/note?path=" + original["path"]) as response:
            rendered = json.load(response)
        assert "<h2>Support</h2>" in rendered["html"]
        assert "<strong>approved</strong>" in rendered["html"]
        assert "<script>" not in rendered["html"]
        assert 'href="javascript:' not in rendered["html"]
        with pytest.raises(HTTPError) as stale:
            post({**change, "body": "Stale text."})
        assert stale.value.code == 409
        assert store.read(original["path"])[1] == rendered["body"]
        with pytest.raises(HTTPError) as event:
            post({**change, "key": original["event"], "revision": 1})
        assert event.value.code == 400
        assert len(store.events(original["path"])) == 2
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_viewer_capture_limits_and_missing_note_errors(store):
    server = make_server(store.root)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(base + "/api/data") as response:
            token = json.load(response)["capability"]

        def post(body):
            with urlopen(
                Request(
                    base + "/api/action",
                    json.dumps(body).encode(),
                    headers={
                        "Content-Type": "application/json",
                        "Origin": base,
                        "X-Brain-Token": token,
                    },
                )
            ) as response:
                return json.load(response)

        created = post(
            {
                "action": "capture",
                "type": "Concept",
                "title": "Support context",
                "body": "Keep the source.",
                "sources": [{"resource": "https://example.org"}],
            }
        )
        assert store.read(created["path"])[0]["type"] == "Concept"
        for body in [
            {
                "action": "capture",
                "type": "Memory Event",
                "title": "Invalid",
                "body": "Invalid event.",
            },
            {
                "action": "edit",
                "key": created["path"],
                "revision": True,
                "title": "Invalid revision",
                "body": "Text",
                "reason": "Test the boundary.",
            },
            {
                "action": "edit",
                "key": "/nodes/absent.md",
                "revision": 1,
                "title": "Missing",
                "body": "Text",
                "reason": "Test the boundary.",
            },
        ]:
            with pytest.raises(HTTPError) as error:
                post(body)
            assert error.value.code == 400
        with pytest.raises(HTTPError) as missing:
            urlopen(base + "/api/note?path=/nodes/absent.md")
        assert missing.value.code == 404
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_named_view_opens_the_selected_space_from_the_shared_root(store, monkeypatch):
    from memora import knowledge as k
    from memora.cli import parser, run
    from memora import live

    k.workspace_create(store, "team", "team")
    monkeypatch.setattr(
        live,
        "view",
        lambda root, no_open, workspace="personal": {
            "root": str(root),
            "workspace": workspace,
            "no_open": no_open,
        },
    )
    result = run(
        parser().parse_args(
            ["--root", str(store.root), "--workspace", "team", "view", "--no-open"]
        )
    )
    assert result == {"root": str(store.root), "workspace": "team", "no_open": True}
