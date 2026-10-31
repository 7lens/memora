"""Exercise the local editor boundary, conflict recovery, and live process."""

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from memora import knowledge as k, obsidian as o
from memora.codec import Conflict, MemoraError, dump
from memora.obsidian_commands import alive, start, stop


def create(store, title="Cache policy", **fields):
    return store.create(
        {
            "type": "Concept",
            "title": title,
            "description": "A local policy.",
            "tags": ["cache"],
            "sources": [{"resource": "https://example.org/policy", "custom": "keep"}],
            "custom": {"nested": [1, "keep"]},
            **fields,
        },
        "Use bounded reads.",
        "agent:test",
        "Keep the policy.",
    )


def editor_path(store, identity):
    return o.directory(store) / o.read_state(store)["entries"][identity]["file"]


def edit(store, identity, *, body=None, **fields):
    path = editor_path(store, identity)
    metadata, old_body = o.read_editor(path.read_text(), path.name)
    metadata.update(fields)
    path.write_text(dump(metadata, old_body if body is None else body))
    return path


def test_vault_inside_project_excludes_activity_and_keeps_source_exact(store):
    note = create(store)
    for kind in ("Task", "Profile", "Checkpoint"):
        store.create(
            {"type": kind, "title": kind},
            "Private activity.",
            "agent:test",
            "Keep local activity.",
        )
    before = store.path(note["path"]).read_bytes()
    result = o.initialize(store)
    assert result["path"] == str(store.root / "obsidian")
    assert result["notes"] == 1
    assert result["issues"] == []
    assert store.path(note["path"]).read_bytes() == before
    assert o.synchronize(store)["updated"] == 0
    assert o.synchronize(store)["imported"] == 0
    assert (o.directory(store) / ".obsidian/app.json").exists()


def test_new_memory_appears_and_source_title_keeps_vault_identity(store):
    a = create(store, "First")
    o.initialize(store)
    original = editor_path(store, a["id"])
    b = create(store, "Second")
    store.update(
        a["path"],
        {
            "title": "New title",
            "brain": {"relations": [{"type": "depends_on", "target": b["path"]}]},
        },
        None,
        "agent:test",
        "Use the current name.",
        1,
    )
    result = o.synchronize(store)
    assert not result["issues"]
    assert result["notes"] == 2
    assert editor_path(store, a["id"]) == original
    assert editor_path(store, b["id"]).exists()
    text = original.read_text()
    assert "title: New title" in text
    assert "[[Notes/Second--" in text
    assert o.synchronize(store)["updated"] == 0


def test_editor_changes_keep_unknown_metadata_audit_and_require_new_publication_review(
    store,
):
    note = create(store)
    target = create(store, "Target")
    proposed = k.propose(
        store, note["path"], 1, "team", "Review the policy.", "agent:test"
    )
    approved = k.approve(
        store,
        note["path"],
        proposed["revision"],
        "human:alice",
        "Review the exact content.",
    )
    o.initialize(store)
    target_link = (
        "[[" + o.read_state(store)["entries"][target["id"]]["file"][:-3] + "]]"
    )
    edit(
        store,
        note["id"],
        title="Edited policy",
        body="Use short reads.",
        tags=["edited"],
        rel_depends_on=[target_link],
    )
    result = o.synchronize(store)
    assert not result["issues"]
    assert result["imported"] == 1
    data, body = store.read(note["path"])
    assert data["brain"]["revision"] == approved["revision"] + 1
    assert data["title"] == "Edited policy"
    assert body.startswith("Use short reads.")
    assert data["custom"] == {"nested": [1, "keep"]}
    assert data["sources"][0]["custom"] == "keep"
    edge = data["brain"]["relations"][0]
    assert edge["target_id"] == target["id"]
    assert data["brain"]["publication"]["state"] == "stale"
    assert not data.get("verified")
    assert store.history(note["path"])[-1]["actor"] == "process:obsidian"
    assert not o.synchronize(store)["imported"]
    assert store.read(note["path"])[0]["brain"]["relations"][0]["id"] == edge["id"]


def test_plain_new_notes_create_private_ideas_and_validation_errors_stay_local(store):
    o.initialize(store)
    path = o.directory(store) / "Notes/New idea.md"
    path.write_text("# Try a bounded cache\n\nMeasure it before adoption.\n")
    assert o.synchronize(store)["imported"] == 1
    notes = list(k.notes(store))
    assert len(notes) == 1
    key, data, _ = notes[0]
    assert data["type"] == "Idea"
    assert data["brain"]["scope"] == "pending"
    assert not data["brain"].get("publication")
    assert not o.synchronize(store)["imported"]
    assert store.read(key)[0]["brain"]["revision"] == 1
    bad = o.directory(store) / "Notes/Unsupported fact.md"
    bad.write_text(
        dump({"type": "Fact", "title": "An unsourced claim"}, "An assertion.")
    )
    assert "Fact needs a source" in o.synchronize(store)["issues"][0]["message"]
    assert len(list(k.notes(store))) == 1


def test_editor_preserves_multiple_historical_relations_not_in_current_catalog(store):
    first, second = create(store, "First"), create(store, "Second")
    note = create(
        store,
        brain={
            "relations": [
                {"type": "historical_relation", "target": first["path"]},
                {"type": "historical_relation", "target": second["path"]},
            ]
        },
    )
    before = store.read(note["path"])[0]["brain"]["relations"]
    o.initialize(store)
    edit(store, note["id"], body="A current contribution.")
    assert not o.synchronize(store)["issues"]
    assert store.read(note["path"])[0]["brain"]["relations"] == before


def test_two_sided_conflict_retains_both_and_resolution_needs_current_revision(store):
    note = create(store)
    o.initialize(store)
    path = edit(store, note["id"], body="Editor contribution.")
    editor_text = path.read_text()
    changed = store.update(
        note["path"],
        {"extra": "current"},
        "Agent contribution.",
        "agent:test",
        "Keep another finding.",
        1,
    )
    result = o.synchronize(store)
    assert "Both Memora and Obsidian changed" in result["issues"][0]["message"]
    assert path.read_text() == editor_text
    assert store.read(note["path"])[1].strip() == "Agent contribution."
    with pytest.raises(Conflict, match="revision changed"):
        o.synchronize(store, (note["id"], "vault", 1))
    resolved = o.synchronize(store, (note["id"], "vault", changed["revision"]))
    assert not resolved["issues"]
    data, body = store.read(note["path"])
    assert data["extra"] == "current"
    assert body.strip() == "Editor contribution."
    assert data["brain"]["revision"] == 3
    assert list((o.cache(store) / "backups").glob("*.md"))


def test_keep_memory_resolution_and_vault_delete_never_delete_memory(store):
    note = create(store)
    o.initialize(store)
    path = edit(store, note["id"], body="Unsaved contribution.")
    changed = store.update(
        note["path"], {}, "Current memory.", "agent:test", "Keep the finding.", 1
    )
    assert o.synchronize(store)["issues"]
    assert not o.synchronize(store, (note["id"], "memory", changed["revision"]))[
        "issues"
    ]
    assert "Current memory." in path.read_text()
    assert len(store.history(note["path"])) == 2
    path.unlink()
    assert "missing" in o.synchronize(store)["issues"][0]["message"]
    assert store.read(note["path"])[0]["brain"]["revision"] == 2
    assert not o.synchronize(store, (note["id"], "memory", 2))["issues"]
    assert path.exists()


@pytest.mark.parametrize(
    "change", ["identity", "revision", "yaml", "publication", "duplicate"]
)
def test_invalid_or_duplicate_edits_do_not_change_memory_and_can_be_restored(
    store, change
):
    note = create(store)
    o.initialize(store)
    path = editor_path(store, note["id"])
    original = store.path(note["path"]).read_bytes()
    if change == "identity":
        metadata, body = o.read_editor(path.read_text(), path.name)
        metadata.pop("memora_id")
        path.write_text(dump(metadata, body))
    elif change == "revision":
        edit(store, note["id"], memora_revision=999, body="Edited.")
    elif change == "yaml":
        path.write_text("---\ntype: [unterminated\n---\nStill here.")
    elif change == "publication":
        edit(store, note["id"], publication="approved")
    else:
        shutil.copyfile(path, path.with_name("Duplicate.md"))
    assert o.synchronize(store)["issues"]
    assert store.path(note["path"]).read_bytes() == original
    assert len(list(k.notes(store))) == 1
    if change in {"identity", "revision", "yaml", "publication"}:
        assert not o.synchronize(store, (note["id"], "memory", 1))["issues"]


def test_new_note_recovery_after_commit_keeps_one_identity_and_revision(
    store, monkeypatch
):
    o.initialize(store)
    (o.directory(store) / "Notes/New idea.md").write_text("A useful idea.")
    replace = o.replace_editor

    def failed(*_args):
        raise OSError("Projection write failed.")

    monkeypatch.setattr(o, "replace_editor", failed)
    assert o.synchronize(store)["issues"]
    monkeypatch.setattr(o, "replace_editor", replace)
    assert not o.synchronize(store)["issues"]
    assert len(list(k.notes(store))) == 1
    assert next(k.notes(store))[1]["brain"]["revision"] == 1


def test_renaming_in_obsidian_keeps_note_identity_and_links(store):
    note = create(store)
    target = create(store, "Target")
    k.relate(
        store,
        note["id"],
        target["id"],
        "supports",
        1,
        "agent:test",
        "Keep the relation.",
    )
    o.initialize(store)
    original = editor_path(store, target["id"])
    renamed = original.with_name("New filename.md")
    original.rename(renamed)
    assert not o.synchronize(store)["issues"]
    assert editor_path(store, target["id"]) == renamed
    assert "[[Notes/New filename]]" in editor_path(store, note["id"]).read_text()
    assert len(list(k.notes(store))) == 2
    assert not o.synchronize(store)["imported"]


def test_recovery_after_commit_before_projection_does_not_duplicate_revision(
    store, monkeypatch
):
    note = create(store)
    o.initialize(store)
    edit(store, note["id"], body="A retained edit.")
    replace = o.replace_editor

    def failed(*_args):
        raise OSError("Projection write failed.")

    monkeypatch.setattr(o, "replace_editor", failed)
    assert o.synchronize(store)["issues"]
    assert store.read(note["path"])[0]["brain"]["revision"] == 2
    monkeypatch.setattr(o, "replace_editor", replace)
    assert not o.synchronize(store)["issues"]
    assert store.read(note["path"])[0]["brain"]["revision"] == 2


def test_edit_during_projection_write_is_retained_as_conflict(store, monkeypatch):
    note = create(store)
    o.initialize(store)
    path = editor_path(store, note["id"])
    store.update(
        note["path"], {}, "Current memory.", "agent:test", "Keep the finding.", 1
    )
    replace = o.replace_editor

    def concurrent(store, path, text, expected):
        metadata, _ = o.read_editor(path.read_text(), path.name)
        path.write_text(dump(metadata, "Concurrent editor change."))
        replace(store, path, text, expected)

    monkeypatch.setattr(o, "replace_editor", concurrent)
    assert "changed during" in o.synchronize(store)["issues"][0]["message"]
    assert "Concurrent editor change." in path.read_text()
    assert store.read(note["path"])[1].strip() == "Current memory."


@pytest.mark.parametrize("timing", ["before_move", "before_install"])
def test_save_between_file_check_and_install_is_never_overwritten(
    store, monkeypatch, timing
):
    note = create(store)
    o.initialize(store)
    path = editor_path(store, note["id"])
    original = path.read_text()
    concurrent = original.replace("Use bounded reads.", "A concurrent save.")
    rename, link = Path.rename, os.link
    if timing == "before_move":

        def racing_rename(self, target):
            if self == path:
                self.write_text(concurrent)
            return rename(self, target)

        monkeypatch.setattr(Path, "rename", racing_rename)
    else:

        def racing_link(source, target):
            if Path(target) == path:
                path.write_text(concurrent)
            return link(source, target)

        monkeypatch.setattr(os, "link", racing_link)
    with pytest.raises(Conflict, match="concurrent save"):
        o.replace_editor(
            store,
            path,
            original.replace("Use bounded reads.", "Current source."),
            original,
        )
    assert path.read_text() == concurrent
    assert list((o.cache(store) / "backups").glob("*.md"))


def test_ignore_and_symlink_boundaries(store, tmp_path):
    subprocess.run(["git", "init", "-q", str(store.root)], check=True)
    (store.root / ".gitignore").write_text("/knowledge/\n")
    with pytest.raises(MemoraError, match="gitignore"):
        o.initialize(store)
    (store.root / ".gitignore").write_text("/knowledge/\n/obsidian/\n")
    assert not o.initialize(store)["issues"]
    outside = tmp_path / "outside.md"
    outside.write_text("Keep this file.")
    (o.directory(store) / "Notes/Unsafe.md").symlink_to(outside)
    with pytest.raises(MemoraError, match="symbolic"):
        o.synchronize(store)
    assert outside.read_text() == "Keep this file."


def eventually(check, seconds=8):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(0.05)
    raise AssertionError("The watcher did not synchronize before the deadline.")


def test_restricted_process_probe_does_not_report_a_live_worker_as_stopped(monkeypatch):
    def denied(_pid, _signal):
        raise PermissionError("The client cannot probe this process.")

    monkeypatch.setattr(os, "kill", denied)
    assert alive({"running": True, "pid": 123}) is True


@pytest.mark.skipif(
    os.name != "posix", reason="The background worker uses POSIX process locks."
)
def test_live_worker_captures_new_memory_and_editor_changes(store, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).resolve().parents[1] / "src"))
    o.initialize(store)
    try:
        running = start(store)
        assert running["running"] is True
        assert start(store)["pid"] == running["pid"]
        note = create(store, "Added while watching")
        eventually(lambda: note["id"] in o.read_state(store)["entries"])
        edit(store, note["id"], body="Changed while watching.")
        eventually(
            lambda: store.read(note["path"])[1].strip() == "Changed while watching."
        )
        assert store.read(note["path"])[0]["brain"]["revision"] == 2
    finally:
        assert stop(store)["running"] is False
