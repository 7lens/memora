import asyncio
import json
import sys

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from memora.codec import MemoraError, Conflict
from memora.context import build_packet
from memora.index import Index
from memora.integrations import doctor, install, uninstall
from memora.service import MemoryService
from memora.sessions import status
from memora.viewer import data as viewer_data, version


def test_relevant_decision_beats_repository_hub_noise(store):
    repo = store.create(
        {"type": "Repository", "title": "Product"}, "", "process:test", "Register."
    )
    chosen = store.create(
        {
            "type": "Decision",
            "title": "Platform membership",
            "description": "Require explicit service membership.",
            "brain": {"repositories": [repo["path"]]},
        },
        "Reason: declared services prevent false asset mappings.",
        "process:test",
        "Keep the rule.",
    )
    for number in range(300):
        store.create(
            {
                "type": "Source",
                "title": f"PR {number}",
                "description": "Unrelated release details.",
                "sources": [{"resource": f"https://example.invalid/pr/{number}"}],
                "brain": {"repositories": [repo["path"]]},
            },
            "Ship a change.",
            "process:test",
            "Keep source.",
        )
    index = Index(store)
    index.refresh()
    packet = build_packet(
        index, "platform membership", store.root, repository=repo["path"]
    )
    notes = [n for n in packet["notes"] if n["type"] != "Repository"]
    assert notes[0]["path"] == chosen["path"]
    assert packet["note_count"] == 1
    assert "declared services prevent false asset mappings" in packet["text"]
    assert packet["text"].encode().__len__() <= 12000
    assert (
        build_packet(index, "platform membership", store.root, repository=repo["path"])
        == packet
    )
    index.close()


def test_foreign_matches_cannot_fill_candidate_limit(store):
    own = store.create(
        {"type": "Repository", "title": "Local"}, "", "process:test", "Register."
    )
    foreign = store.create(
        {"type": "Repository", "title": "Other"}, "", "process:test", "Register."
    )
    local = store.create(
        {
            "type": "Concept",
            "title": "Memory context",
            "brain": {"repositories": [own["path"]]},
        },
        "Local rules.",
        "process:test",
        "Keep concept.",
    )
    for i in range(260):
        store.create(
            {
                "type": "Fact",
                "title": f"Memory context {i}",
                "brain": {"repositories": [foreign["path"]]},
            },
            "Foreign facts.",
            "process:test",
            "Keep source.",
        )
    index = Index(store)
    index.refresh()
    packet = build_packet(index, "memory context", store.root, repository=own["path"])
    assert local["path"] in packet["text"]
    assert "Foreign facts" not in packet["text"]
    index.close()


def test_receipt_logs_real_context_reads_and_private_updates(store):
    service = MemoryService(store)
    assert status(store)["state"] == "no_context_calls"
    result = service.context("platform", store.root)
    session_id = result["receipt"]["session_id"]
    saved = service.remember(
        session_id,
        "Decision",
        "Declare platform members",
        "Use declared links.",
        "Reason: explicit links prevent invalid mappings.",
        "Keep the decision.",
    )
    full = service.get_note(saved["path"], session_id)
    assert full["metadata"]["brain"]["state"] == "provisional"
    reused = service.remember(
        session_id,
        "Decision",
        "Declare platform members",
        "Use declared links.",
        "Reason: explicit links prevent invalid mappings.",
        "Keep decision.",
    )
    assert reused["state"] == "existing_note"
    assert reused["matches"][0]["path"] == saved["path"]
    with pytest.raises(Conflict):
        service.remember(
            session_id,
            "Decision",
            "Declare platform members",
            "Use declared links.",
            "Reason: explicit links matter.",
            "Update.",
            path=saved["path"],
            revision=50,
        )
    refreshed = service.context("platform", store.root, session_id=session_id)
    assert refreshed["note_count"] == 1
    records = status(store, session_id)["sessions"][0]["events"]
    assert [e["kind"] for e in records] == [
        "context_returned",
        "knowledge_saved",
        "note_returned",
        "context_returned",
    ]
    assert records[-1]["notes"] == refreshed["notes"]
    assert "not verified" in refreshed["receipt"]["claim"]


def test_fact_needs_source_and_decision_needs_reason(store):
    service = MemoryService(store)
    session_id = service.context("facts", store.root)["receipt"]["session_id"]
    with pytest.raises(MemoraError, match="source"):
        service.remember(
            session_id, "Fact", "Assertion", "A claim.", "Claim content.", "Save."
        )
    with pytest.raises(MemoraError, match="reason"):
        service.remember(
            session_id, "Decision", "Choice", "A choice.", "Use the choice.", "Save."
        )
    with pytest.raises(MemoraError, match="checkpoint"):
        service.remember(
            session_id, "Checkpoint", "Progress", "Work.", "Continue.", "Save."
        )


def test_mcp_conversation_uses_same_service_and_receipts(store):
    async def conversation():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "memora", "--root", str(store.root), "mcp"],
        )
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as client:
                await client.initialize()
                tools = await client.list_tools()
                assert {t.name for t in tools.tools} == {
                    "start_task",
                    "recall",
                    "get_note",
                    "remember",
                    "session_status",
                }
                started = await client.call_tool(
                    "start_task", {"cwd": str(store.root), "task": "platform rules"}
                )
                assert not started.isError
                context = started.structuredContent
                session_id = context["receipt"]["session_id"]
                saved = await client.call_tool(
                    "remember",
                    {
                        "session_id": session_id,
                        "kind": "Decision",
                        "title": "Use declared links",
                        "description": "Keep the membership rule.",
                        "body": "Reason: explicit membership prevents invalid assets.",
                        "reason": "Keep the choice.",
                    },
                )
                assert not saved.isError
                path = saved.structuredContent["path"]
                read = await client.call_tool(
                    "get_note", {"path": path, "session_id": session_id}
                )
                assert (
                    not read.isError and "membership" in read.structuredContent["body"]
                )
                recalled = await client.call_tool(
                    "recall", {"session_id": session_id, "task": "declared links"}
                )
                assert (
                    not recalled.isError
                    and recalled.structuredContent["note_count"] == 1
                )
                reported = await client.call_tool(
                    "session_status", {"session_id": session_id}
                )
                assert not reported.isError
                assert reported.structuredContent == status(store, session_id)
                failed = await client.call_tool(
                    "get_note", {"path": "/nodes/missing.md", "session_id": session_id}
                )
                assert failed.isError

    asyncio.run(conversation())


def test_installation_does_not_claim_context_use_and_preserves_settings(
    store, tmp_path
):
    home = tmp_path / "home"
    toml = home / ".codex/config.toml"
    toml.parent.mkdir(parents=True)
    original = '# Keep this comment.\nmodel = "example"\n[mcp_servers.other]\ncommand = "other"\n'
    toml.write_text(original)
    install(store, home, "codex", transport="mcp")
    assert "# Keep this comment." in toml.read_text()
    assert 'command = "other"' in toml.read_text()
    assert "memora" in toml.read_text()
    report = doctor(store, home)
    assert report["usage"]["state"] == "no_context_calls"
    assert next(e for e in report["editors"] if e["editor"] == "codex")[
        "mcp_configured"
    ]
    toml.write_text(toml.read_text() + '\n[extra]\nvalue = "user change"\n')
    uninstall(store, home, "codex")
    assert "memora" not in toml.read_text()
    assert 'value = "user change"' in toml.read_text()
    assert "# Keep this comment." in toml.read_text()


def test_conflicting_mcp_config_fails_before_instruction_changes(store, tmp_path):
    home = tmp_path / "home"
    path = home / ".gemini/config/mcp_config.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"mcpServers": {"memora": {"command": "foreign"}}}))
    with pytest.raises(MemoraError, match="another configuration"):
        install(store, home, transport="mcp")
    assert not (home / ".codex/AGENTS.md").exists()


def test_session_data_updates_viewer_etag_and_exposes_external_graph(store):
    ref = {
        "provider": "external-graph",
        "instance": "customer-demo",
        "entity_type": "platform",
        "entity_id": "payments",
        "relation": "documents",
        "observed_revision": "4",
    }
    store.create(
        {
            "type": "Concept",
            "title": "Platform notes",
            "brain": {"external_refs": [ref]},
        },
        "Describe the platform.",
        "process:test",
        "Save.",
    )
    index = Index(store)
    index.refresh()
    before = version(index)
    MemoryService(store).context("platform", store.root)
    index.refresh()
    graph = viewer_data(index)
    assert before != version(index)
    assert graph["sessions"][0]["events"][0]["kind"] == "context_returned"
    external = next(n for n in graph["nodes"] if n["type"] == "ExternalReference")
    assert "No connector" in external["description"]
    assert any(
        e["target"] == external["path"] and e["kind"] == "documents"
        for e in graph["edges"]
    )
    index.close()


def test_optional_semantic_failure_reports_text_search_and_keeps_context(store):
    store.create(
        {"type": "Concept", "title": "Platform definition"},
        "A platform groups declared technologies.",
        "process:test",
        "Save.",
    )
    (store.cache / "semantic.json").write_text(
        '{"enabled":true,"model":"missing","revision":"invalid","path":"/missing"}'
    )
    index = Index(store)
    index.refresh()
    result = build_packet(index, "platform", store.root)
    assert result["note_count"] == 1
    assert result["search"]["mode"] == "text+graph"
    assert result["search"]["semantic"] == "unavailable"
    assert result["search"]["error"]
    index.close()


def test_context_excerpts_and_revisions_use_one_index_snapshot(store):
    note = store.create(
        {"type": "Concept", "title": "Snapshot concept"},
        "Before change.",
        "process:test",
        "Save.",
    )
    index = Index(store)
    index.refresh()
    store.update(note["path"], {}, "After change.", "process:test", "Update.", 1)
    old = build_packet(index, "snapshot", store.root)
    selected = next(n for n in old["notes"] if n["path"] == note["path"])
    assert selected["revision"] == 1 and "Before change." in old["text"]
    assert "After change." not in old["text"]
    index.refresh()
    updated = build_packet(index, "snapshot", store.root)
    assert "After change." in updated["text"]
    index.close()


def test_session_cannot_read_foreign_scope_or_change_directory(store, tmp_path):
    service = MemoryService(store)
    first = service.context("local task", store.root)
    session_id = first["receipt"]["session_id"]
    foreign = store.create(
        {"type": "Repository", "title": "Foreign"}, "", "process:test", "Register."
    )
    note = store.create(
        {
            "type": "Concept",
            "title": "Foreign rule",
            "brain": {"repositories": [foreign["path"]]},
        },
        "Do not cross task scope.",
        "process:test",
        "Save.",
    )
    with pytest.raises(MemoraError, match="another task scope"):
        service.get_note(note["path"], session_id)
    with pytest.raises(MemoraError, match="change repository"):
        service.context("foreign", tmp_path, session_id=session_id)


def test_remember_preserves_unknown_fields_sources_and_relations(store):
    service = MemoryService(store)
    initial = service.context("rule", store.root)
    session_id = initial["receipt"]["session_id"]
    saved = service.remember(
        session_id,
        "Concept",
        "Rule",
        "A rule.",
        "First content.",
        "Save.",
        sources=[{"resource": "conversation:first"}],
    )
    store.update(
        saved["path"],
        {
            "vendor_field": {"keep": True},
            "brain": {
                "relations": [{"type": "documents", "target": initial["repository"]}]
            },
        },
        None,
        "process:test",
        "Add metadata.",
        1,
    )
    updated = service.remember(
        session_id,
        "Concept",
        "Rule",
        "New description.",
        "New content.",
        "Update.",
        sources=[{"resource": "conversation:next"}],
        path=saved["path"],
        revision=2,
    )
    assert updated["revision"] == 3
    metadata, body = store.read(saved["path"])
    assert metadata["vendor_field"] == {"keep": True}
    assert len(metadata["sources"]) == 2
    assert metadata["brain"]["relations"][0]["target"] == initial["repository"]
    assert "New content" in body


def test_doctor_probe_passes_real_mcp_without_claiming_task_use(store, tmp_path):
    from memora.cli import parser, run

    result = run(
        parser().parse_args(
            ["--root", str(store.root), "--home", str(tmp_path), "doctor", "--probe"]
        )
    )
    assert result["mcp"]["state"] == "connection_verified"
    assert result["usage"]["state"] == "no_context_calls"
    assert status(store)["state"] == "no_context_calls"


def test_legacy_repository_scope_reuses_notes_without_repeating_inherited_project(
    store,
):
    project = store.create(
        {"type": "Project", "title": "Team context"}, "", "process:test", "Register."
    )
    repo = store.create(
        {
            "type": "Repository",
            "title": "Source",
            "brain": {"projects": [project["path"]]},
        },
        "",
        "process:test",
        "Register.",
    )
    old = store.create(
        {
            "type": "Concept",
            "title": "Same subject",
            "brain": {"repositories": [repo["path"]]},
        },
        "Existing knowledge.",
        "process:test",
        "Save.",
    )
    service = MemoryService(store)
    initial = service.context("same subject", store.root, repository=repo["path"])
    session_id = initial["receipt"]["session_id"]
    matched = service.remember(
        session_id,
        "Concept",
        "Same subject",
        "More detail.",
        "Reviewed knowledge.",
        "Review.",
    )
    assert matched["state"] == "existing_note"
    assert matched["matches"] == [{"path": old["path"], "revision": 1}]
    changed = service.remember(
        session_id,
        "Concept",
        "Same subject",
        "More detail.",
        "Reviewed knowledge.",
        "Review.",
        path=old["path"],
        revision=1,
    )
    assert changed["revision"] == 2
    assert store.read(old["path"])[0]["brain"].get("projects", []) == []
