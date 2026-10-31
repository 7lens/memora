"""Remote exchange keeps local edits, review boundaries, and recovery data."""

import copy
import json
import uuid
from pathlib import Path

import pytest
from memora import knowledge as k
from memora.codec import MemoraError, Conflict
from memora.remote import (
    canonical,
    seal,
    apply_pull,
    read_config,
    save_config,
    secure_url,
    export_v2,
)


def entry(identity=None, revision=1, state="published"):
    identity = identity or str(uuid.uuid4())
    return {
        "id": identity,
        "origin": str(uuid.uuid4()),
        "revision": revision,
        "state": state,
        "record": {
            "id": identity,
            "type": "Concept",
            "title": "Support policy",
            "description": "Policy",
            "body": "Use a source.",
            "sources": [{"resource": "https://example.org/policy"}],
            "origin": {"workspace": "team", "revision": 1},
            "review": {"by": "human:alice", "at": "2026-10-16T10:00:00Z"},
        },
        "relations": [],
        "actor": "user:alice",
        "time": "2026-10-16T10:00:00Z",
        "reviewer": "user:alice",
    }


def test_canonical_cross_language_fixture():
    path = Path(__file__).parent / "fixtures/knowledge"
    value = json.loads((path / "canonical.json").read_text())
    assert canonical(value).decode() == (path / "canonical.txt").read_text().strip()
    assert seal(value) == seal(dict(reversed(list(value.items()))))
    with pytest.raises(ValueError):
        canonical({"invalid": float("nan")})


def test_pull_updates_unmodified_notes_and_keeps_unknown_fields(store):
    remote = {"space": str(uuid.uuid4()), "cursor": 0, "baselines": {}}
    save_config(store, {"team": remote})
    first = entry()
    assert (
        apply_pull(store, "team", remote, [{"entry": first, "cursor": 1}], 1)[
            "received"
        ]
        == 1
    )
    path, data, body = k.find(store, first["id"])
    assert body.strip() == "Use a source."
    # A remote retry does not add a local event.
    revision = data["brain"]["revision"]
    assert (
        apply_pull(store, "team", remote, [{"entry": first, "cursor": 1}], 1)[
            "received"
        ]
        == 0
    )
    assert store.read(path)[0]["brain"]["revision"] == revision
    next_entry = copy.deepcopy(first)
    next_entry["revision"] = 2
    next_entry["record"]["body"] = "A later policy."
    apply_pull(store, "team", remote, [{"entry": next_entry, "cursor": 2}], 2)
    data, body = store.read(path)
    assert body.strip() == "A later policy."
    assert data["brain"]["revision"] > revision
    assert read_config(store)["team"]["cursor"] == 2


def test_pull_preserves_local_edits_and_full_incoming_conflict(store):
    remote = {"space": str(uuid.uuid4()), "cursor": 0, "baselines": {}}
    save_config(store, {"team": remote})
    first = entry()
    apply_pull(store, "team", remote, [{"entry": first, "cursor": 1}], 1)
    path, data, _ = k.find(store, first["id"])
    store.update(
        path,
        {},
        "Local edit.",
        "agent:test",
        "Keep the local change.",
        data["brain"]["revision"],
    )
    other = copy.deepcopy(first)
    other["revision"] = 2
    other["record"]["body"] = "Remote edit."
    with pytest.raises(Conflict):
        apply_pull(store, "team", remote, [{"entry": other, "cursor": 2}], 2)
    assert store.read(path)[1].strip() == "Local edit."
    assert read_config(store)["team"]["cursor"] == 1
    report = json.loads((store.cache / "remote-team-conflicts.json").read_text())
    assert report["incoming"][first["id"]]["record"]["body"] == "Remote edit."


def test_pull_withdrawal_keeps_note_and_history(store):
    remote = {"space": str(uuid.uuid4()), "cursor": 0, "baselines": {}}
    save_config(store, {"team": remote})
    first = entry()
    apply_pull(store, "team", remote, [{"entry": first, "cursor": 1}], 1)
    withdrawn = {**first, "revision": 2, "state": "withdrawn"}
    apply_pull(store, "team", remote, [{"entry": withdrawn, "cursor": 2}], 2)
    _, data, body = k.find(store, first["id"])
    assert data["brain"]["state"] == "discarded"
    assert body.strip() == "Use a source."


def test_export_v2_requires_review_and_excludes_private_work(store):
    note = store.create(
        {"type": "Concept", "title": "Support", "description": "Policy"},
        "Public context.",
        "agent:test",
        "Keep context.",
    )
    with pytest.raises(MemoraError):
        export_v2(store, "team")
    candidate = k.propose(
        store, note["path"], note["revision"], "team", "Share context.", "agent:test"
    )
    k.approve(
        store,
        note["path"],
        candidate["revision"],
        "human:alice",
        "Review exact content.",
    )
    value = export_v2(store, "team")
    assert value["format"] == "context-knowledge-v2"
    assert str(uuid.UUID(value["origin"])) == value["origin"]
    assert len(value["records"]) == 1
    assert "events" not in value
    assert value == seal(value)


@pytest.mark.parametrize(
    "url",
    [
        "https://user:secret@example.org",
        "http://example.org",
        "https://example.org?token=secret",
        "file:///tmp/test",
    ],
)
def test_credentials_require_a_trusted_endpoint(url):
    with pytest.raises(MemoraError):
        secure_url(url)


def test_login_uses_pkce_state_and_private_credentials(store, monkeypatch):
    import threading
    import socket
    from urllib.parse import parse_qs, urlsplit
    from urllib.request import urlopen
    from memora import remote as r

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    config = {
        "domain": "https://identity.example.org",
        "client_id": "cli",
        "scope": "test/access",
        "url": "https://graph.example.org",
        "redirect_uri": f"http://127.0.0.1:{port}/callback",
    }
    seen = {}
    threads = []

    def browser(url):
        parameters = parse_qs(urlsplit(url).query)
        assert parameters["code_challenge_method"] == ["S256"]
        assert parameters["resource"] == [config["url"]]
        seen["challenge"] = parameters["code_challenge"][0]

        def callback():
            # Invalid state must not finish the login.
            from urllib.error import HTTPError

            try:
                urlopen(config["redirect_uri"] + "?code=bad&state=wrong", timeout=3)
            except HTTPError as error:
                assert error.code == 400
            with urlopen(
                config["redirect_uri"] + "?code=valid&state=" + parameters["state"][0],
                timeout=3,
            ) as response:
                assert response.status == 200

        thread = threading.Thread(target=callback)
        thread.start()
        threads.append(thread)

    def exchange(url, body=None, token=None, form=False):
        import base64
        import hashlib

        assert url.endswith("/oauth2/token") and form
        assert body["code"] == "valid"
        challenge = (
            base64.urlsafe_b64encode(
                hashlib.sha256(body["code_verifier"].encode()).digest()
            )
            .decode()
            .rstrip("=")
        )
        assert challenge == seen["challenge"]
        return {
            "access_token": "test-access",
            "refresh_token": "test-refresh",
            "expires_in": 300,
        }

    monkeypatch.setattr(r.webbrowser, "open", browser)
    monkeypatch.setattr(r, "request", exchange)
    assert r.login(store, "team", config)["signed_in"]
    for thread in threads:
        thread.join(timeout=3)
    path = store.cache / "remote-team-credentials.json"
    assert path.stat().st_mode & 0o077 == 0
    assert json.loads(path.read_text())["access_token"] == "test-access"


def test_remote_stage_failure_does_not_write_partial_notes(store):
    remote = {"space": str(uuid.uuid4()), "cursor": 0, "baselines": {}}
    save_config(store, {"team": remote})
    first = entry()
    bad = entry()
    bad["record"]["type"] = "Checkpoint"
    with pytest.raises(MemoraError):
        apply_pull(
            store,
            "team",
            remote,
            [{"entry": first, "cursor": 1}, {"entry": bad, "cursor": 2}],
            2,
        )
    assert list(k.notes(store)) == []
    assert read_config(store)["team"]["cursor"] == 0


def test_explicit_conflict_resolution_accepts_the_selected_remote_version(store):
    from argparse import Namespace
    from memora.remote import dispatch

    remote = {"space": str(uuid.uuid4()), "cursor": 0, "baselines": {}}
    save_config(store, {"team": remote})
    first = entry()
    apply_pull(store, "team", remote, [{"entry": first}], 1)
    path, data, _ = k.find(store, first["id"])
    store.update(
        path,
        {},
        "My local change.",
        "agent:test",
        "Keep a change.",
        data["brain"]["revision"],
    )
    changed = copy.deepcopy(first)
    changed["revision"] = 2
    changed["record"]["body"] = "The incoming change."
    with pytest.raises(Conflict):
        apply_pull(store, "team", remote, [{"entry": changed}], 2)
    dispatch(
        store, Namespace(action="resolve", name="team", id=first["id"], take="remote")
    )
    assert store.read(path)[1].strip() == "The incoming change."
    assert not (store.cache / "remote-team-conflicts.json").exists()


def test_pull_preserves_provenance_and_republication_restores_visibility(store):
    remote = {"space": str(uuid.uuid4()), "cursor": 0, "baselines": {}}
    save_config(store, {"team": remote})
    first = entry()
    first["record"]["provenance"] = {
        "created_by": "agent:source",
        "created_at": "2026-10-16T09:00:00Z",
    }
    apply_pull(store, "team", remote, [{"entry": first}], 1)
    withdrawn = {**first, "revision": 2, "state": "withdrawn"}
    apply_pull(store, "team", remote, [{"entry": withdrawn}], 2)
    restored = {**first, "revision": 4}
    older = {**first, "revision": 3}
    # Select the highest version even if a provider returns rows out of order.
    apply_pull(store, "team", remote, [{"entry": restored}, {"entry": older}], 4)
    _, data, _ = k.find(store, first["id"])
    assert data["brain"]["state"] == "provisional"
    assert data["brain"]["provenance"] == first["record"]["provenance"]
    assert remote["baselines"][first["id"]]["revision"] == 4
    with pytest.raises(MemoraError, match="backwards"):
        apply_pull(store, "team", remote, [], 3)


def test_pull_rejects_draft_bodies_and_invalid_records_before_any_write(store):
    remote = {"space": str(uuid.uuid4()), "cursor": 0, "baselines": {}}
    first = entry()
    first["state"] = "proposed"
    with pytest.raises(MemoraError, match="entry"):
        apply_pull(store, "team", remote, [{"entry": first}], 1)
    assert list(k.notes(store)) == []
    first["state"] = "published"
    first["record"]["type"] = "Profile"
    with pytest.raises(MemoraError):
        apply_pull(store, "team", remote, [{"entry": first}], 1)
    assert list(k.notes(store)) == []


def test_pull_rejects_origin_rebinding_and_equal_revision_content_conflicts(store):
    remote = {"space": str(uuid.uuid4()), "cursor": 0, "baselines": {}}
    save_config(store, {"team": remote})
    first = entry()
    other = copy.deepcopy(first)
    other["record"]["body"] = "Conflicting same-version content."
    with pytest.raises(MemoraError, match="conflicting"):
        apply_pull(store, "team", remote, [{"entry": first}, {"entry": other}], 1)
    assert list(k.notes(store)) == []
    apply_pull(store, "team", remote, [{"entry": first}], 1)
    other = {**first, "revision": 2, "origin": str(uuid.uuid4())}
    with pytest.raises(Conflict, match="origin"):
        apply_pull(store, "team", remote, [{"entry": other}], 2)
    assert remote["cursor"] == 1


def test_push_retry_recovers_baselines_after_a_committed_idempotent_import(
    store, monkeypatch
):
    from memora import remote as r, standard
    from memora.cli import parser

    space = str(uuid.uuid4())
    note = store.create(
        {"type": "Concept", "title": "Retry policy", "description": "Policy."},
        "Retry safely.",
        "agent:test",
        "Keep the policy.",
    )
    p = k.propose(
        store, note["path"], note["revision"], space, "Share the policy.", "agent:test"
    )
    k.approve(store, note["path"], p["revision"], "human:fixture", "Review the policy.")
    config = {
        "url": "http://127.0.0.1:1",
        "space": space,
        "local": True,
        "cursor": 0,
        "baselines": {},
        "protocol": standard.FORMAT,
    }
    save_config(store, {"team": config})
    package = standard.export_package(store, space)
    row = {
        "id": note["id"],
        "record": package["records"][0],
        "origin": package["origin"],
        "revision": 3,
        "relations": [],
        "state": "published",
    }

    def respond(url, body=None, token=None):
        if url.endswith("/imports"):
            return {"items": [], "unchanged": 1, "cursor": 3}
        assert url.endswith("/records/" + note["id"])
        return row

    monkeypatch.setattr(r, "request", respond)
    r.dispatch(store, parser().parse_args(["remote", "push", "team"]))
    base = read_config(store)["team"]["baselines"][note["id"]]
    assert base["revision"] == 3
    assert base["origin"] == package["origin"]
    assert (
        base["fingerprint"]
        == store.read(note["path"])[0]["brain"]["publication"]["fingerprint"]
    )


def test_pull_refuses_a_non_advancing_paginated_feed(store, monkeypatch):
    from memora import remote as r
    from memora.cli import parser

    save_config(
        store,
        {
            "team": {
                "url": "http://127.0.0.1:1",
                "space": str(uuid.uuid4()),
                "local": True,
                "cursor": 0,
                "baselines": {},
            }
        },
    )
    monkeypatch.setattr(
        r, "request", lambda *_args, **_kwargs: {"items": [], "cursor": 0, "more": True}
    )
    with pytest.raises(MemoraError, match="advance"):
        r.dispatch(store, parser().parse_args(["remote", "pull", "team"]))


def test_remote_validity_reaches_retrieval_and_can_be_extended(store):
    from memora.codec import score

    remote = {"space": str(uuid.uuid4()), "cursor": 0, "baselines": {}}
    save_config(store, {"team": remote})
    first = entry()
    first["record"]["provenance"] = {"valid_until": "2020-01-01T00:00:00Z"}
    apply_pull(store, "team", remote, [{"entry": first}], 1)
    _, metadata, body = k.find(store, first["id"])
    assert score(metadata, body, at="2026-10-31T00:00:00Z")["stale"] is True
    later = copy.deepcopy(first)
    later["revision"] = 2
    later["record"]["provenance"]["valid_until"] = "2030-01-01T00:00:00Z"
    apply_pull(store, "team", remote, [{"entry": later}], 2)
    _, metadata, body = k.find(store, first["id"])
    assert score(metadata, body, at="2026-10-31T00:00:00Z")["stale"] is False
