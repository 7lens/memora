"""Knowledge workflows through the same service used by CLI and viewer."""

import json
import threading
import uuid
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from memora import knowledge as k
from memora.cli import parser, run, validate
from memora.codec import MemoraError, Conflict, dump, score
from memora.index import Index
from memora.integrations import install, uninstall
from memora.live import make_server
from memora.service import MemoryService
from memora.sessions import feedback, read
from memora.viewer import data as viewer_data


def entity(store, title="Payments", kind="service"):
    result = store.create(
        {
            "type": "Entity",
            "title": title,
            "description": title,
            "tags": [kind],
            "brain": {"entity_kind": kind, "scope": "shared"},
        },
        "Public context.",
        "process:test",
        "Add a subject.",
    )
    return result, store.read(result["path"])[0]["brain"]["id"]


def observation(store, subject, **extra):
    arguments = dict(
        title="The service uses a vendor",
        subject=subject,
        predicate="vendor",
        value="Vendor A",
        basis="reported",
        sources=[{"resource": "https://example.org/evidence"}],
        actor="agent:test",
        reason="Keep the source claim.",
    )
    arguments.update(extra)
    return k.observe(store, **arguments)


def publish(store, note, destination="team"):
    data, _ = store.read(note["path"])
    candidate = k.propose(
        store,
        note["path"],
        data["brain"]["revision"],
        destination,
        "Useful team context.",
        "agent:test",
    )
    approved = k.approve(
        store,
        note["path"],
        candidate["revision"],
        "human:reviewer",
        "Review the exact content.",
    )
    return approved


def test_identities_survive_title_and_file_changes(store):
    first, identity = entity(store)
    second, _ = entity(store, "Vendor", "organization")
    linked = k.relate(
        store,
        first["path"],
        second["path"],
        "depends_on",
        1,
        "agent:test",
        "Keep the dependency.",
    )
    edge_id = linked["relation"]["id"]
    store.update(
        first["path"], {"title": "New title"}, None, "process:test", "Rename.", 2
    )
    moved = "/nodes/moved.md"
    store.path(second["path"]).rename(store.path(moved))
    index = Index(store)
    index.refresh()
    node = index.row(first["path"])
    assert node["id"] == identity and node["relations"][0]["target"] == moved
    assert node["relations"][0]["id"] == edge_id
    assert validate(store)["valid"]
    assert len(store.history(moved)) == 1
    index.close()
    with pytest.raises(MemoraError, match="identity cannot change"):
        store.update(
            first["path"],
            {"brain": {"id": str(uuid.uuid4())}},
            None,
            "process:test",
            "Change identity.",
            3,
        )


def test_observations_describe_entities_and_relations(store):
    first, identity = entity(store)
    other, _ = entity(store, "Vendor", "organization")
    linked = k.relate(
        store,
        first["path"],
        other["path"],
        "depends_on",
        1,
        "agent:test",
        "Link the subjects.",
    )
    obs = observation(store, identity)
    relation_obs = observation(
        store,
        linked["relation"]["id"],
        subject_kind="relation",
        predicate="criticality",
        value="high",
    )
    assert (
        store.read(obs["path"])[0]["brain"]["observation"]["subject"]["id"] == identity
    )
    index = Index(store)
    index.refresh()
    graph = viewer_data(index)
    assert any(n["type"] == "Relation" for n in graph["nodes"])
    assert any(
        e["origin"] == relation_obs["path"] and e["target"].startswith("relation:")
        for e in graph["edges"]
    )
    assert validate(store)["valid"]
    index.close()


def test_inference_and_expiry_are_not_confirmed_evidence(store):
    _, identity = entity(store)
    obs = observation(
        store,
        identity,
        basis="inferred",
        sources=[],
        observed_at="2025-01-01T00:00:00Z",
        valid_until="2025-02-01T00:00:00Z",
    )
    data, body = store.read(obs["path"])
    assert data["brain"]["state"] == "provisional"
    assert score(data, body)["score"] == 25 and score(data, body)["stale"]
    with pytest.raises(MemoraError, match="needs a source"):
        observation(store, identity, sources=[])
    with pytest.raises(MemoraError, match="validity end"):
        observation(
            store,
            identity,
            observed_at="2025-02-01T00:00:00Z",
            valid_until="2025-01-01T00:00:00Z",
        )
    with pytest.raises(MemoraError, match="does not exist"):
        observation(store, str(uuid.uuid4()))


def test_contradictions_keep_sources_and_history(store):
    _, identity = entity(store)
    first = observation(store, identity)
    second = observation(
        store,
        identity,
        value="Vendor B",
        sources=[{"resource": "https://example.org/new"}],
    )
    k.relate(
        store,
        second["path"],
        first["path"],
        "contradicts",
        1,
        "agent:test",
        "Sources disagree.",
    )
    index = Index(store)
    index.refresh()
    assert index.row(first["path"])["score"] == 25
    assert store.read(first["path"])[0]["sources"][0]["resource"].endswith("evidence")
    assert len(store.events(second["path"])) == 2
    index.close()


def test_profile_and_previous_work_return_without_a_repository(store):
    profile = store.create(
        {
            "type": "Profile",
            "title": "Working preferences",
            "brain": {"scope": "shared"},
        },
        "Use short status updates. Explain decisions.",
        "human:owner",
        "Save my preferences.",
    )
    checkpoint = run(
        parser().parse_args(
            [
                "--root",
                str(store.root),
                "checkpoint",
                "--session",
                "previous",
                "--goal",
                "Review vendor concentration",
                "--progress",
                "Read the vendor sources.",
                "--next",
                "Check service dependencies.",
                "--reason",
                "Resume in another chat.",
            ]
        )
    )
    result = MemoryService(store).context("vendor concentration")
    assert result["repository"] is None and result["code"]["root"] is None
    assert store.read(checkpoint["path"])[0]["brain"]["context"]["revision"] is None
    assert not validate(store)["errors"]
    assert profile["path"] in result["text"] and checkpoint["path"] in result["text"]
    assert len(result["text"].encode()) <= 12000
    used = feedback(
        store,
        result["receipt"]["session_id"],
        profile["path"],
        "used",
        "Apply the communication preference.",
    )
    assert used["kind"] == "context_feedback"
    assert not store.read(profile["path"])[0].get("verified")
    assert read(store, result["receipt"]["session_id"])["cwd"] is None


def test_entity_context_and_workspace_isolation(store):
    subject, identity = entity(store)
    obs = observation(store, identity)
    k.workspace_create(store, "team", "team")
    team = k.select_workspace(store, "team")
    result = MemoryService(store).context("unrelated words", entity=identity)
    assert subject["path"] in result["text"] and obs["path"] in result["text"]
    assert MemoryService(team).context("Payments")["notes"] == []
    with pytest.raises(MemoraError):
        MemoryService(team).get_note(subject["path"])
    with pytest.raises(MemoraError):
        k.workspace_create(store, "../escape", "team")
    assert k.workspace(team)["kind"] == "team"


def test_sharing_needs_human_review_and_excludes_private_history(store, tmp_path):
    note, identity = entity(store)
    store.update(
        note["path"], {}, "PRIVATE OLD TEXT", "process:test", "Private draft.", 1
    )
    store.update(
        note["path"], {}, "Current safe summary.", "process:test", "Replace draft.", 2
    )
    candidate = k.propose(
        store,
        note["path"],
        3,
        "team",
        "Share a summary.",
        "agent:test",
        "Reviewed short text.",
    )
    with pytest.raises(MemoraError, match="human review"):
        k.approve(store, note["path"], candidate["revision"], "agent:test", "Approve.")
    approved = k.approve(
        store,
        note["path"],
        candidate["revision"],
        "human:owner",
        "I reviewed this text.",
    )
    assert score(*store.read(note["path"]))["score"] == 25
    output = tmp_path / "reviewed.json"
    package = k.export_shared(store, "team", output)
    encoded = output.read_text()
    assert package["records"][0]["id"] == identity
    assert "Reviewed short text." in encoded
    assert "PRIVATE OLD TEXT" not in encoded and "Current safe summary." not in encoded
    assert "events" not in package and note["path"] not in encoded
    store.update(
        note["path"],
        {},
        "Changed content.",
        "agent:test",
        "Change the claim.",
        approved["revision"],
    )
    with pytest.raises(Conflict, match="new review"):
        k.export_shared(store, "team")


def test_observation_export_requires_subject_and_safe_sources(store):
    subject, identity = entity(store)
    obs = observation(store, identity)
    publish(store, obs)
    with pytest.raises(MemoraError, match="subject"):
        k.export_shared(store, "team")
    publish(store, subject)
    package = k.export_shared(store, "team")
    assert len(package["records"]) == 2
    assert all(
        "publication" not in n and "verified" not in n for n in package["records"]
    )


def test_shared_import_is_idempotent_and_rejects_divergence(store, tmp_path):
    subject, _ = entity(store)
    publish(store, subject)
    output = tmp_path / "shared.json"
    k.export_shared(store, "team", output)
    k.workspace_create(store, "team", "team")
    team = k.select_workspace(store, "team")
    assert k.import_shared(team, output)["imported"] == 1
    assert k.import_shared(team, output)["unchanged"] == 1
    key, data, _ = next(k.notes(team))
    team.update(
        key,
        {},
        "A local correction.",
        "human:reviewer",
        "Correct the claim.",
        data["brain"]["revision"],
    )
    with pytest.raises(Conflict, match="diverged"):
        k.import_shared(team, output)
    with pytest.raises(MemoraError, match="destination"):
        k.import_shared(store, output)


def test_migration_previews_and_keeps_exact_backup(store):
    path = "/nodes/legacy.md"
    legacy = {
        "type": "Concept",
        "title": "Legacy context",
        "vendor": {"keep": True},
        "brain": {"revision": 1, "scope": "shared"},
    }
    raw = dump(legacy, "Existing content.")
    store.path(path).parent.mkdir(exist_ok=True)
    store.path(path).write_text(raw)
    assert k.migrate(store)["notes"] == 1
    assert store.path(path).read_text() == raw
    result = k.migrate(store, True)
    from pathlib import Path

    assert (Path(result["backup"]) / "knowledge/nodes/legacy.md").read_text() == raw
    assert store.read(path)[0]["vendor"] == {"keep": True}
    assert store.read(path)[0]["brain"]["id"]
    assert k.migrate(store, True)["notes"] == 0


def test_cli_default_install_has_no_mcp_entry(store, tmp_path, monkeypatch):
    home = tmp_path / "home"
    install(store, home, "codex")
    assert not (home / ".codex/config.toml").exists()
    assert "start --task" in (home / ".codex/AGENTS.md").read_text()
    import sys
    from memora.integrations import doctor

    with monkeypatch.context() as changed:
        changed.setattr(sys, "executable", "/another/link/to/python")
        assert next(
            e for e in doctor(store, home)["editors"] if e["editor"] == "codex"
        )["pointer_present"]
    install(store, home, "codex", transport="mcp")
    assert "memora" in (home / ".codex/config.toml").read_text()
    install(store, home, "codex")
    assert "memora" not in (home / ".codex/config.toml").read_text()
    install(store, home, "codex")
    uninstall(store, home, "codex")


def test_viewer_capture_review_and_origin_checks(store):
    server = make_server(store.root)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(base + "/api/data") as response:
            token = json.load(response)["capability"]

        def post(body, **headers):
            request = Request(
                base + "/api/action",
                json.dumps(body).encode(),
                headers={
                    "Content-Type": "application/json",
                    "Origin": base,
                    "X-Brain-Token": token,
                    **headers,
                },
            )
            with urlopen(request) as response:
                return json.load(response)

        saved = post(
            {
                "action": "entity",
                "title": "Business service",
                "kind": "service",
                "body": "Service context.",
            }
        )
        with urlopen(base + "/api/note?path=" + saved["path"]) as response:
            full = json.load(response)
        assert full["body"] == "Service context.\n"
        obs = post(
            {
                "action": "observe",
                "title": "Service state",
                "subject": full["metadata"]["brain"]["id"],
                "predicate": "state",
                "value": "ready",
                "basis": "reported",
                "sources": [{"resource": "https://example.org"}],
            }
        )
        assert store.read(obs["path"])[0]["type"] == "Observation"
        candidate = post(
            {
                "action": "propose",
                "key": saved["path"],
                "revision": 1,
                "destination": "team",
                "reason": "Share context.",
            }
        )
        post(
            {
                "action": "approve",
                "key": saved["path"],
                "revision": candidate["revision"],
                "reason": "Reviewed.",
            }
        )
        package = post({"action": "export", "destination": "team"})
        assert package["records"][0]["title"] == "Business service"
        with pytest.raises(HTTPError) as error:
            post(
                {"action": "entity", "title": "Foreign", "kind": "service"},
                Origin="https://foreign.example",
            )
        assert error.value.code == 403
        with pytest.raises(HTTPError) as error:
            post(
                {
                    "action": "approve",
                    "key": saved["path"],
                    "revision": 1,
                    "reason": "Stale.",
                },
                **{"X-Brain-Token": "wrong"},
            )
        assert error.value.code == 403
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_only_explicit_project_relations_expand_context(store):
    first = store.create(
        {"type": "Project", "title": "Service program"},
        "",
        "agent:test",
        "Define scope.",
    )
    second = store.create(
        {"type": "Project", "title": "Vendor program"},
        "",
        "agent:test",
        "Define scope.",
    )
    note = store.create(
        {
            "type": "Fact",
            "title": "Vendor support dependency",
            "brain": {"projects": [second["path"]]},
        },
        "The vendor supports the shared service.",
        "agent:test",
        "Keep context.",
    )
    service = MemoryService(store)
    before = service.context("vendor support", project=first["path"])
    assert note["path"] not in before["text"]
    k.relate(
        store,
        first["path"],
        second["path"],
        "depends_on",
        1,
        "agent:test",
        "The projects share vendor work.",
    )
    after = service.context("vendor support", project=first["path"])
    assert note["path"] in after["text"]
    assert (
        note["path"]
        in service.context(
            "vendor evidence", session_id=after["receipt"]["session_id"]
        )["text"]
    )


def test_pending_work_remains_available_during_recall(store):
    checkpoint = store.create(
        {
            "type": "Checkpoint",
            "title": "Pending vendor review",
            "brain": {"work_state": "open", "context": {"session": "old"}},
        },
        "Check vendor evidence.",
        "agent:test",
        "Keep work.",
    )
    service = MemoryService(store)
    packet = service.context("vendor review")
    assert checkpoint["path"] in packet["text"]
    recalled = service.context(
        "vendor evidence", session_id=packet["receipt"]["session_id"]
    )
    assert checkpoint["path"] in recalled["text"]


def test_observation_keeps_subject_scope(store):
    project = store.create(
        {"type": "Project", "title": "Private program"},
        "",
        "agent:test",
        "Define scope.",
    )
    other = store.create(
        {"type": "Project", "title": "Other program"}, "", "agent:test", "Define scope."
    )
    subject = store.create(
        {
            "type": "Entity",
            "title": "Scoped service",
            "brain": {"entity_kind": "service", "projects": [project["path"]]},
        },
        "",
        "agent:test",
        "Keep subject.",
    )
    obs = observation(store, subject["path"])
    assert store.read(obs["path"])[0]["brain"]["projects"] == [project["path"]]
    packet = MemoryService(store).context("vendor", project=other["path"])
    assert obs["path"] not in packet["text"]


def test_projection_drops_unknown_private_metadata_and_checks_review_revision(store):
    _, identity = entity(store)
    obs = observation(store, identity)
    store.update(
        obs["path"],
        {"brain": {"observation": {"private_detail": "HIDDEN METADATA"}}},
        None,
        "agent:test",
        "Add private context.",
        1,
    )
    candidate = k.propose(
        store, obs["path"], 2, "team", "Share the claim.", "agent:test"
    )
    assert "HIDDEN METADATA" not in json.dumps(
        store.read(obs["path"])[0]["brain"]["publication"]["projection"]
    )
    with pytest.raises(Conflict):
        k.approve(
            store, obs["path"], candidate["revision"] - 1, "human:owner", "Review."
        )
    with pytest.raises(MemoraError, match="cannot be published"):
        profile = store.create(
            {"type": "Profile", "title": "Private preferences"},
            "",
            "agent:test",
            "Keep preferences.",
        )
        k.propose(store, profile["path"], 1, "team", "Share.", "agent:test")


def test_publication_review_does_not_invalidate_source_evidence(store):
    from memora.cli import verify
    from types import SimpleNamespace

    note = store.create(
        {
            "type": "Fact",
            "title": "Current claim",
            "sources": [{"resource": "https://example.org"}],
        },
        "A supported claim.",
        "agent:test",
        "Record the claim.",
    )
    verify(
        store,
        SimpleNamespace(
            path=note["path"],
            revision=1,
            actor="human:owner",
            reason="Confirm this claim.",
            evidence=None,
            independent=False,
        ),
    )
    assert score(*store.read(note["path"]))["score"] == 90
    publish(store, note)
    assert score(*store.read(note["path"]))["score"] == 90


def test_relation_observations_round_trip_with_external_references(store, tmp_path):
    first, _ = entity(store)
    second, _ = entity(store, "Vendor", "organization")
    ref = {
        "provider": "example",
        "instance": "customer",
        "entity_type": "service",
        "entity_id": "payments",
        "relation": "documents",
        "private_field": "DO NOT EXPORT",
    }
    store.update(
        first["path"],
        {"brain": {"external_refs": [ref]}},
        None,
        "agent:test",
        "Link the external subject.",
        1,
    )
    linked = k.relate(
        store,
        first["path"],
        second["path"],
        "depends_on",
        2,
        "agent:test",
        "Keep the dependency.",
    )
    obs = observation(store, linked["relation"]["id"], subject_kind="relation")
    for note in [first, second, obs]:
        publish(store, note)
    output = tmp_path / "relations.json"
    package = k.export_shared(store, "team", output)
    assert len(package["relations"]) == 1 and "DO NOT EXPORT" not in output.read_text()
    k.workspace_create(store, "team", "team")
    team = k.select_workspace(store, "team")
    assert k.import_shared(team, output)["imported"] == 3
    assert k.import_shared(team, output)["unchanged"] == 3
    assert validate(team)["valid"]


def test_invalid_shared_record_leaves_the_whole_target_unchanged(store, tmp_path):
    first, _ = entity(store)
    second, _ = entity(store, "Vendor", "organization")
    publish(store, first)
    publish(store, second)
    package = k.export_shared(store, "team")
    package["records"][-1]["type"] = "Profile"
    from memora.codec import digest, json_text

    package.pop("sha256")
    package["sha256"] = digest(json_text(package))
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(package))
    k.workspace_create(store, "team", "team")
    team = k.select_workspace(store, "team")
    with pytest.raises(MemoraError):
        k.import_shared(team, path)
    assert list(k.notes(team)) == []
    assert not (team.cache / "import-transaction.json").exists()


def test_default_cli_path_does_not_import_mcp(store):
    import subprocess
    import sys

    script = """
import sys
class NoMCP:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'mcp' or fullname.startswith('mcp.'):
            raise AssertionError('The default path imported MCP')
sys.meta_path.insert(0, NoMCP())
from memora.cli import parser, run
result = run(parser().parse_args(['--root', sys.argv[1], 'start', '--task', 'general context']))
assert result['repository'] is None and result['receipt']['state'] == 'context_returned'
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(store.root)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_moved_note_private_backup_keeps_stable_identity_and_history(store, tmp_path):
    from memora.bundles import export_bundle, import_bundle
    from memora.store import Store

    note, identity = entity(store)
    new_path = "/nodes/renamed.md"
    store.path(note["path"]).rename(store.path(new_path))
    package = tmp_path / "private.json"
    export_bundle(store, package)
    target = Store(tmp_path / "restored")
    assert import_bundle(target, package)["state"] == "imported"
    assert target.read(new_path)[0]["brain"]["id"] == identity
    assert len(target.history(new_path)) == 1


def test_general_chat_finds_project_knowledge_without_a_repository(store):
    project = store.create(
        {"type": "Project", "title": "Vendor program"},
        "",
        "agent:test",
        "Define scope.",
    )
    note = store.create(
        {
            "type": "Fact",
            "title": "Vendor renewal decision",
            "brain": {"projects": [project["path"]]},
        },
        "The renewal review needs current support evidence.",
        "agent:test",
        "Keep project knowledge.",
    )
    packet = MemoryService(store).context("vendor renewal")
    assert packet["repository"] is None
    assert note["path"] in packet["text"] and "Scope: Vendor program" in packet["text"]
    assert next(n for n in packet["notes"] if n["path"] == note["path"])[
        "projects"
    ] == [project["path"]]
