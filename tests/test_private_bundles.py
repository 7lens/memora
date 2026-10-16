import json
import shutil

import pytest

from memora.bundles import export_bundle, import_bundle
from memora.codec import MemoraError
from memora.store import Store


def other_store(store, tmp_path):
    root = tmp_path / "other"
    root.mkdir()
    shutil.copytree(store.root / "docs", root / "docs")
    return Store(root)


def test_private_bundle_preserves_notes_events_unknown_fields_and_refs(store, tmp_path):
    ref = {
        "provider": "external-graph",
        "instance": "demo",
        "entity_type": "service",
        "entity_id": "compute",
        "relation": "explains",
    }
    note = store.create(
        {
            "type": "Concept",
            "title": "Compute service",
            "vendor_extension": {"keep": True},
            "brain": {"external_refs": [ref]},
        },
        "A shared capability.",
        "process:test",
        "Save.",
    )
    store.update(
        note["path"],
        {"description": "Service context."},
        None,
        "process:test",
        "Explain.",
        1,
    )
    (store.cache / "secrets.json").write_text('{"password":"excluded"}')
    (store.cache / "sessions").mkdir()
    (store.cache / "sessions/a.json").write_text('{"not":"exported"}')
    file = tmp_path / "private.json"
    export_bundle(store, file)
    assert (
        "password" not in file.read_text()
        and '"not": "exported"' not in file.read_text()
    )
    destination = other_store(store, tmp_path)
    imported = import_bundle(destination, file)
    assert imported["state"] == "imported"
    assert destination.read(note["path"])[0]["vendor_extension"] == {"keep": True}
    assert destination.read(note["path"])[0]["brain"]["external_refs"] == [ref]
    assert store.events(note["path"]) == destination.events(note["path"])
    assert import_bundle(destination, file)["imported"] == 0
    second = tmp_path / "second.json"
    export_bundle(destination, second)
    assert (
        json.loads(second.read_text())["notes"][0]["id"]
        == json.loads(file.read_text())["notes"][0]["id"]
    )


def test_bundle_conflicts_abort_all_writes_and_keep_a_private_report(store, tmp_path):
    note = store.create(
        {"type": "Concept", "title": "Stable identity"},
        "Original.",
        "process:test",
        "Save.",
    )
    file = tmp_path / "first.json"
    export_bundle(store, file)
    destination = other_store(store, tmp_path)
    import_bundle(destination, file)
    destination.update(
        note["path"],
        {},
        "Different local decision.",
        "process:test",
        "Local change.",
        1,
    )
    store.update(
        note["path"],
        {},
        "Different remote decision.",
        "process:test",
        "Other change.",
        1,
    )
    added = store.create(
        {"type": "Idea", "title": "Do not partly import"},
        "Pending.",
        "process:test",
        "Save.",
    )
    file = tmp_path / "next.json"
    export_bundle(store, file)
    report = import_bundle(destination, file)
    assert report["state"] == "conflict" and report["imported"] == 0
    assert report["conflicts"]
    assert destination.read(note["path"])[1].strip() == "Different local decision."
    assert not destination.path(added["path"]).exists()


def test_bundle_accepts_linear_advances_with_exact_history(store, tmp_path):
    note = store.create(
        {"type": "Concept", "title": "Evolution"}, "First.", "process:test", "Save."
    )
    first = tmp_path / "first.json"
    export_bundle(store, first)
    destination = other_store(store, tmp_path)
    import_bundle(destination, first)
    store.update(note["path"], {}, "Second.", "process:test", "Update.", 1)
    second = tmp_path / "second.json"
    export_bundle(store, second)
    assert import_bundle(destination, second)["state"] == "imported"
    assert destination.read(note["path"])[0]["brain"]["revision"] == 2
    assert store.events(note["path"]) == destination.events(note["path"])


@pytest.mark.parametrize("corruption", ["checksum", "path", "event", "identity"])
def test_bundle_rejects_corrupt_or_unsafe_input_before_writing(
    store, tmp_path, corruption
):
    note = store.create(
        {"type": "Concept", "title": "Input"}, "Content.", "process:test", "Save."
    )
    file = tmp_path / "input.json"
    export_bundle(store, file)
    package = json.loads(file.read_text())
    if corruption == "checksum":
        package["notes"][0]["content"] += "modified"
    elif corruption == "path":
        package["notes"][0]["path"] = "/../outside.md"
    elif corruption == "event":
        package["events"] = []
    else:
        package["notes"][0]["id"] = "invalid"
    file.write_text(json.dumps(package))
    destination = other_store(store, tmp_path)
    with pytest.raises(MemoraError):
        import_bundle(destination, file)
    assert not destination.path(note["path"]).exists()


def test_export_refuses_to_put_private_memory_in_software_repository(store):
    with pytest.raises(MemoraError, match="outside"):
        export_bundle(store, store.root / "private.json")


def test_interrupted_import_recovers_notes_and_immutable_events(
    store, tmp_path, monkeypatch
):
    import memora.bundles as bundles

    note = store.create(
        {"type": "Concept", "title": "Recover import"},
        "Keep the complete history.",
        "process:test",
        "Save.",
    )
    source = tmp_path / "recover.json"
    export_bundle(store, source)
    destination = other_store(store, tmp_path)
    original_atomic = bundles.atomic
    failed = False

    def fail_after_note(path, text):
        nonlocal failed
        original_atomic(path, text)
        if not failed and path == destination.path(note["path"]):
            failed = True
            raise OSError("Simulated process interruption.")

    with monkeypatch.context() as patch:
        patch.setattr(bundles, "atomic", fail_after_note)
        with pytest.raises(OSError, match="interruption"):
            import_bundle(destination, source)
    assert (destination.cache / "import-transaction.json").exists()
    with destination.lock():
        pass
    assert not (destination.cache / "import-transaction.json").exists()
    assert destination.read(note["path"]) == store.read(note["path"])
    assert destination.events(note["path"]) == store.events(note["path"])


def test_import_recovery_preserves_unrelated_external_edits(
    store, tmp_path, monkeypatch
):
    import memora.bundles as bundles
    from memora.codec import Conflict

    note = store.create(
        {"type": "Concept", "title": "Review recovery"},
        "Original.",
        "process:test",
        "Save.",
    )
    source = tmp_path / "input.json"
    export_bundle(store, source)
    destination = other_store(store, tmp_path)
    original_atomic = bundles.atomic

    def stop_before_files(path, text):
        if path == destination.path(note["path"]):
            raise OSError("Interrupted before import.")
        return original_atomic(path, text)

    with monkeypatch.context() as patch:
        patch.setattr(bundles, "atomic", stop_before_files)
        with pytest.raises(OSError):
            import_bundle(destination, source)
    destination.path(note["path"]).parent.mkdir(parents=True, exist_ok=True)
    destination.path(note["path"]).write_text("Unrelated external edit.")
    with pytest.raises(Conflict, match="external change"):
        with destination.lock():
            pass
    assert destination.path(note["path"]).read_text() == "Unrelated external edit."
    assert (destination.cache / "import-transaction.json").exists()


def test_same_content_with_another_origin_cannot_replace_local_identity(
    store, tmp_path
):
    import uuid

    note = store.create(
        {"type": "Concept", "title": "Private identity"},
        "Same content.",
        "process:test",
        "Save.",
    )
    first = tmp_path / "original.json"
    export_bundle(store, first)
    original = json.loads(first.read_text())
    original["notes"][0]["id"] = str(uuid.uuid4()) + ":" + note["path"]
    foreign = tmp_path / "foreign.json"
    foreign.write_text(json.dumps(original))
    assert import_bundle(store, foreign)["state"] == "conflict"
    second = tmp_path / "unchanged.json"
    export_bundle(store, second)
    assert (
        json.loads(second.read_text())["notes"][0]["id"]
        == json.loads(first.read_text())["notes"][0]["id"]
    )
