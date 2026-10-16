from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from memora.cli import verify
from memora.codec import (
    MemoraError,
    Conflict,
    content_hash,
    dump,
    load,
    relations,
    graph_relations,
    score,
)
from memora.index import Index
from memora.store import atomic


@pytest.mark.parametrize(
    "kind",
    [
        "Idea",
        "Concept",
        "Fact",
        "Decision",
        "Task",
        "Procedure",
        "Document",
        "System",
        "Project",
        "Repository",
        "Source",
        "Checkpoint",
    ],
)
def test_types_round_trip(store, kind):
    result = store.create(
        {
            "type": kind,
            "title": kind,
            "description": "A test entity.",
            "vendor": {"unknown": [None, True, "é", {"nested": 4}]},
            "brain": {"custom": {"value": "kept"}},
        },
        "A note.",
        "process:test",
        "Check the type.",
    )
    data, _body = store.read(result["path"])
    assert data["vendor"]["unknown"][3] == {"nested": 4}
    store.update(
        result["path"],
        {"title": "New title"},
        None,
        "process:test",
        "Change the title.",
        1,
    )
    new, _ = store.read(result["path"])
    assert new["brain"]["custom"]["value"] == "kept"
    assert new["vendor"] == data["vendor"]
    assert store.path(result["path"]).exists()


def test_new_type_needs_catalog(store):
    with pytest.raises(MemoraError, match="type"):
        store.create(
            {"type": "Experiment", "title": "A trial"},
            "",
            "process:test",
            "Add the trial.",
        )
    path = store.root / "docs/types.md"
    data, body = load(path.read_text())
    data["brain"]["types"]["Experiment"] = "A controlled trial of a hypothesis."
    atomic(path, dump(data, body))
    result = store.create(
        {"type": "Experiment", "title": "A trial"}, "", "process:test", "Add the trial."
    )
    assert store.read(result["path"])[0]["type"] == "Experiment"


def test_relations_round_trip_reverse_and_unknown_target(store, note):
    result = store.create(
        {
            "type": "Idea",
            "title": "Cache design",
            "description": "A possible design.",
            "brain": {
                "relations": [
                    {"type": "supports", "target": note["path"]},
                    {"type": "documents", "target": "/nodes/missing.md"},
                ]
            },
        },
        "See [the fact](<" + note["path"] + ">).",
        "process:test",
        "Link the idea.",
    )
    data, body = store.read(result["path"])
    assert len(relations(data, body, result["path"])) == 2
    idx = Index(store)
    idx.refresh()
    assert idx.neighbors(note["path"])[0]["path"] == result["path"]
    assert idx.unknown_links() == [
        {"origin": result["path"], "target": "/nodes/missing.md", "kind": "documents"}
    ]
    idx.close()


def test_project_and_repository_scopes_create_graph_edges(store):
    project = store.create(
        {"type": "Project", "title": "Project scope"},
        "",
        "process:test",
        "Add the project.",
    )
    repo = store.create(
        {
            "type": "Repository",
            "title": "Repository scope",
            "brain": {"projects": [project["path"]]},
        },
        "",
        "process:test",
        "Add the repository.",
    )
    note = store.create(
        {
            "type": "Fact",
            "title": "Scoped fact",
            "brain": {
                "projects": [project["path"]],
                "repositories": [repo["path"]],
                "relations": [{"type": "belongs_to", "target": repo["path"]}],
            },
        },
        "",
        "process:test",
        "Add the scoped fact.",
    )
    data, body = store.read(note["path"])
    edges = graph_relations(data, body, note["path"])
    assert {(edge["type"], edge["target"]) for edge in edges} == {
        ("belongs_to", project["path"]),
        ("belongs_to", repo["path"]),
    }
    idx = Index(store)
    idx.refresh()
    assert {n["path"] for n in idx.neighbors(project["path"])} >= {
        repo["path"],
        note["path"],
    }
    assert {n["path"] for n in idx.neighbors(repo["path"])} >= {note["path"]}
    idx.close()


def test_relation_disagreement_is_visible(store, note):
    result = store.create(
        {
            "type": "Idea",
            "title": "Design",
            "brain": {"relations": [{"type": "supports", "target": note["path"]}]},
        },
        "",
        "process:test",
        "Link the design.",
    )
    path = store.path(result["path"])
    path.write_text(path.read_text().replace("- supports:", "- contradicts:"))
    with pytest.raises(MemoraError, match="do not match"):
        store.read(result["path"])
    idx = Index(store)
    with pytest.raises(MemoraError):
        idx.refresh()
    idx.close()


@pytest.mark.parametrize(
    "path",
    [
        "/../outside.md",
        "/nodes/../../outside.md",
        "/nodes/index.md",
        "/nodes/a\\b.md",
        "/nodes/%2e%2e/out.md",
    ],
)
def test_paths_cannot_escape_bundle(store, path):
    with pytest.raises(MemoraError):
        store.path(path)


def test_scope_paths_are_validated_at_write(store):
    with pytest.raises(MemoraError, match="paths must start"):
        store.create(
            {
                "type": "Concept",
                "title": "Unsafe scope",
                "brain": {"projects": ["../bad.md"]},
            },
            "",
            "process:test",
            "Reject an unsafe scope.",
        )


def test_symlink_cannot_escape_bundle(store, tmp_path):
    outside = tmp_path / "outside.md"
    outside.write_text("outside")
    (store.bundle / "link.md").symlink_to(outside)
    with pytest.raises(MemoraError):
        store.read("/link.md")


def test_concurrent_update_has_one_winner(store, note):
    def change(i):
        try:
            return store.update(
                note["path"],
                {"description": f"Change {i}."},
                None,
                "process:test",
                "Change the note.",
                1,
            )
        except Conflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(change, [1, 2]))
    assert sum(r is not None for r in results) == 1
    assert store.read(note["path"])[0]["brain"]["revision"] == 2
    assert len(store.events(note["path"])) == 2


def test_history_and_log(store, note):
    first = store.events(note["path"])[0]
    store.update(
        note["path"],
        {"description": "A new claim."},
        None,
        "process:test",
        "Replace the claim.",
        1,
    )
    before = store.history(note["path"], first["at"])
    assert load(before)[0]["description"] == "The cache reduces repeated reads."
    events = store.history(note["path"])
    assert [e["revision"] for e in events] == [1, 2]
    assert "before" not in events[0]
    log = (store.bundle / "log.md").read_text()
    assert first["at"][:10] in log and first["path"] in log
    with pytest.raises(MemoraError, match="immutable"):
        store.update(first["path"], {}, None, "process:test", "Change the event.", 1)


def test_recover_after_interruption(store, note, monkeypatch):
    original = store.recover
    calls = 0

    def fail():
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("Power loss")
        original()

    monkeypatch.setattr(store, "recover", fail)
    with pytest.raises(OSError):
        store.update(
            note["path"],
            {"title": "Recovered note"},
            None,
            "process:test",
            "Change the title.",
            1,
        )
    assert (store.cache / "transaction.json").exists()
    monkeypatch.setattr(store, "recover", original)
    with store.lock():
        pass
    assert store.read(note["path"])[0]["title"] == "Recovered note"
    assert len(store.events(note["path"])) == 2
    assert not (store.cache / "transaction.json").exists()


def test_recovery_does_not_overwrite_external_edit(store, note, monkeypatch):
    original = store.recover
    calls = 0

    def fail():
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("Power loss")
        original()

    monkeypatch.setattr(store, "recover", fail)
    with pytest.raises(OSError):
        store.update(
            note["path"],
            {"title": "Pending"},
            None,
            "process:test",
            "Change the title.",
            1,
        )
    store.path(note["path"]).write_text("External work")
    monkeypatch.setattr(store, "recover", original)
    with pytest.raises(Conflict), store.lock():
        pass
    assert store.path(note["path"]).read_text() == "External work"


def test_scores_checks_expiry_and_invalidation(store, note, tmp_path):
    data, body = store.read(note["path"])
    assert score(data, body)["score"] == 25
    evidence = tmp_path / "result.txt"
    evidence.write_text("The source check passed.")
    args = SimpleNamespace(
        path=note["path"],
        actor="process:checker",
        reason="The source matches.",
        evidence=evidence,
        independent=True,
        revision=1,
    )
    verify(store, args)
    data, body = store.read(note["path"])
    assert score(data, body)["score"] == 75
    args.actor = "human:user"
    args.reason = "The user confirmed this claim."
    args.revision = 2
    args.independent = False
    args.evidence = None
    verify(store, args)
    data, body = store.read(note["path"])
    assert score(data, body)["score"] == 100
    store.update(
        note["path"],
        {"brain": {"state": "settled", "work_state": "done"}},
        None,
        "process:test",
        "Complete the task.",
        3,
    )
    data, body = store.read(note["path"])
    assert score(data, body)["score"] == 100
    assert score(data, body, contradicted=True)["score"] == 25
    data["stale_after"] = "2020-01-01T00:00:00Z"
    # Expiry limits the score after a fresh check of the same content.
    data["verified"][0]["brain"]["content_hash"] = content_hash(data, body)
    data["verified"][1]["brain"]["content_hash"] = content_hash(data, body)
    assert score(data, body)["score"] == 50
    store.update(
        note["path"],
        {"description": "Changed content."},
        None,
        "process:test",
        "Correct the content.",
        4,
    )
    data, body = store.read(note["path"])
    assert score(data, body)["score"] == 50


def test_changed_evidence_invalidates_check(store, note, tmp_path):
    evidence = tmp_path / "result.txt"
    evidence.write_text("A source result.")
    args = SimpleNamespace(
        path=note["path"],
        actor="process:test",
        reason="Check the source.",
        evidence=evidence,
        independent=False,
        revision=1,
    )
    verify(store, args)
    idx = Index(store)
    idx.refresh()
    assert idx.row(note["path"])["score"] == 75
    data, _ = store.read(note["path"])
    resource = data["verified"][0]["brain"]["evidence"]["resource"]
    (store.bundle / resource.lstrip("/")).write_text("Changed artifact")
    assert idx.row(note["path"])["score"] == 50
    idx.close()


def test_imported_bare_verification_preserved(store):
    result = store.create(
        {
            "type": "Fact",
            "title": "Imported",
            "sources": [{"resource": "https://example.com/schema"}],
            "verified": {"by": "human:user", "at": "2026-10-06T12:00:00Z"},
        },
        "",
        "process:import",
        "Import the source note.",
    )
    data, body = store.read(result["path"])
    assert data["verified"]["by"] == "human:user"
    # An imported review lacks the local content binding. Keep it, but do not invent a current check.
    assert score(data, body)["score"] == 50


def test_contradiction_caps_both_nodes(store, note):
    other = store.create(
        {
            "type": "Fact",
            "title": "Other claim",
            "sources": [{"resource": "https://example.com"}],
            "brain": {"relations": [{"type": "contradicts", "target": note["path"]}]},
        },
        "",
        "process:test",
        "Record the conflict.",
    )
    idx = Index(store)
    idx.refresh()
    assert idx.row(other["path"])["score"] == 25
    assert idx.row(note["path"])["score"] == 25
    store.update(
        other["path"],
        {"brain": {"state": "discarded"}},
        None,
        "process:test",
        "The claim is false.",
        1,
    )
    idx.refresh()
    assert "A contradiction is open." not in idx.row(note["path"])["reasons"]
    idx.close()


def test_index_round_trip_and_external_changes(store, note):
    idx = Index(store)
    idx.refresh()
    assert idx.read_count == 1
    assert idx.search("cache")[0]["path"] == note["path"]
    idx.read_count = 0
    idx.refresh()
    assert idx.read_count == 0
    assert idx.search('" OR * cache')[0]["path"] == note["path"]
    idx.close()
    (store.cache / "index.sqlite").unlink()
    idx = Index(store)
    idx.refresh()
    assert idx.search("cache")[0]["path"] == note["path"]
    idx.close()


def test_corrupt_note_does_not_return_empty_results(store, note):
    idx = Index(store)
    idx.refresh()
    store.path(note["path"]).write_text("Broken source")
    with pytest.raises(MemoraError):
        idx.refresh()
    idx.close()


def test_memory_write_needs_ignored_knowledge_directory(store):
    import subprocess

    subprocess.run(
        ["git", "init", "-b", "main", str(store.root)], check=True, capture_output=True
    )
    with pytest.raises(MemoraError, match="ignore the full knowledge directory"):
        store.create(
            {"type": "Idea", "title": "Private idea"},
            "",
            "process:test",
            "Keep the idea.",
        )
    assert not list(store.bundle.glob("nodes/*.md"))
    (store.root / ".gitignore").write_text("/knowledge/\n")
    result = store.create(
        {"type": "Idea", "title": "Private idea"}, "", "process:test", "Keep the idea."
    )
    assert store.path(result["path"]).exists()


def test_memory_write_requires_the_full_knowledge_tree_to_be_ignored(store):
    import subprocess

    subprocess.run(
        ["git", "init", "-b", "main", str(store.root)], check=True, capture_output=True
    )
    (store.root / ".gitignore").write_text("/knowledge/nodes/\n")
    with pytest.raises(MemoraError, match="ignore the full knowledge directory"):
        store.require_ignored_memory()


def test_memory_write_requires_repository_gitignore_not_local_exclude(store):
    import subprocess

    subprocess.run(
        ["git", "init", "-b", "main", str(store.root)], check=True, capture_output=True
    )
    info_exclude = store.root / ".git" / "info" / "exclude"
    info_exclude.write_text("/knowledge/\n")
    with pytest.raises(MemoraError, match="ignore the full knowledge directory"):
        store.require_ignored_memory()


def test_evidence_cannot_leave_bundle(store, note, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (store.bundle / "references").symlink_to(outside, target_is_directory=True)
    evidence = tmp_path / "result.txt"
    evidence.write_text("The source matches.")
    args = SimpleNamespace(
        path=note["path"],
        actor="process:test",
        reason="Check the source.",
        evidence=evidence,
        independent=False,
        revision=1,
    )
    with pytest.raises(MemoraError, match="leaves the knowledge bundle"):
        verify(store, args)
    assert list(outside.iterdir()) == []
