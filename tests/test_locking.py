"""Exercise lock lifetime with real threads, processes, and interrupted writes."""

from concurrent.futures import ThreadPoolExecutor
import json
import multiprocessing
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest

from memora.cli import parser, run
from memora.codec import Conflict, MemoraError
from memora.index import Index
from memora.locking import is_locked
from memora.store import Store


def process(store, script, *args):
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
    return subprocess.Popen(
        [
            sys.executable,
            "-u",
            "-c",
            "import sys, time\nfrom pathlib import Path\nfrom memora.store import Store\ns = Store(Path(sys.argv[1]))\n"
            + script,
            str(store.root),
            *map(str, args),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )


def ready(child, path):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if path.exists():
            return
        if child.poll() is not None:
            raise AssertionError(child.communicate())
        time.sleep(0.01)
    raise AssertionError("The child did not reach its synchronization point.")


def finish(child):
    if child.poll() is None:
        child.kill()
    child.communicate(timeout=10)


@pytest.mark.parametrize("failure", ["body", "owner", "recovery"])
def test_exception_at_each_acquisition_stage_releases_kernel_lock(
    store, monkeypatch, failure
):
    import memora.store as module

    original_atomic, original_recover = module.atomic, store.recover
    if failure == "owner":

        def fail(path, text):
            if path.name == "write-owner.json":
                raise OSError("Owner metadata write failed.")
            original_atomic(path, text)

        monkeypatch.setattr(module, "atomic", fail)
    elif failure == "recovery":

        def fail():
            raise OSError("Recovery failed.")

        monkeypatch.setattr(store, "recover", fail)
    with pytest.raises(OSError), store.lock(timeout=0.1):
        raise OSError("Operation failed.")
    monkeypatch.setattr(module, "atomic", original_atomic)
    monkeypatch.setattr(store, "recover", original_recover)
    with Store(store.root).lock(timeout=0):
        pass
    assert (store.cache / "write.lock").is_file()


def test_nested_locks_share_one_owner_across_store_instances_and_index(store):
    with store.lock(timeout=0):
        owner = (store.cache / "write-owner.json").read_text()
        with Store(store.root).lock(timeout=0):
            note = store.create(
                {"type": "Concept", "title": "Nested note"},
                "A local note.",
                "process:test",
                "Keep the note.",
            )
            index = Index(store)
            try:
                index.refresh()
                assert len(index.all()) == 1
            finally:
                index.close()
        assert (store.cache / "write-owner.json").read_text() == owner
    assert store.read(note["path"])[0]["brain"]["revision"] == 1


@pytest.mark.parametrize("kill", [False, True])
def test_process_death_releases_lock_without_cleanup_even_with_stale_owner(store, kill):
    marker = store.cache / "ready"
    child = process(
        store,
        "with s.lock():\n    (s.cache / 'ready').write_text('ready')\n    time.sleep(60)\n",
    )
    try:
        ready(child, marker)
        with pytest.raises(Conflict, match="busy"), store.lock(timeout=0.05):
            pytest.fail("A live lock must remain exclusive.")
        if kill:
            child.kill()
        else:
            child.terminate()
        child.wait(timeout=10)
        inode = (store.cache / "write.lock").stat().st_ino
        with store.lock(timeout=0.5):
            pass
        assert (store.cache / "write.lock").stat().st_ino == inode
    finally:
        finish(child)


def test_live_kernel_owner_cannot_be_stolen_based_on_dead_pid_metadata(store):
    marker = store.cache / "ready"
    child = process(
        store,
        "with s.lock():\n    (s.cache / 'ready').write_text('ready')\n    time.sleep(60)\n",
    )
    try:
        ready(child, marker)
        (store.cache / "write-owner.json").write_text(json.dumps({"pid": 2147483647}))
        for _ in range(2):
            with pytest.raises(Conflict, match="busy"), store.lock(timeout=0.03):
                pytest.fail("Owner metadata must not override the kernel lock.")
    finally:
        finish(child)
    with store.lock(timeout=0.1):
        pass


def test_threads_are_exclusive_and_waiters_do_not_leak_ownership(store):
    inside = 0
    completed = []
    gate = threading.Barrier(6)

    def writer(worker):
        nonlocal inside
        gate.wait(timeout=10)
        for turn in range(15):
            with Store(store.root).lock():
                inside += 1
                assert inside == 1
                time.sleep(0.001)
                completed.append((worker, turn))
                inside -= 1

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(writer, range(6)))
    assert len(set(completed)) == 90
    with store.lock(timeout=0):
        pass


def test_thread_timeout_does_not_unlock_the_owner(store):
    with store.lock():

        def contender():
            with (
                pytest.raises(Conflict, match="thread"),
                Store(store.root).lock(timeout=0.03),
            ):
                pytest.fail("A second thread entered the lock.")

        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(contender).result(timeout=10)
    with store.lock(timeout=0):
        pass


@pytest.mark.parametrize("legacy", [False, True])
def test_multiple_processes_write_and_index_without_lost_notes_or_events(store, legacy):
    if legacy:
        child = subprocess.Popen([sys.executable, "-c", "pass"])
        child.wait(timeout=10)
        (store.cache / "write.lock").mkdir()
        (store.cache / "write.lock/owner.json").write_text(
            json.dumps({"pid": child.pid})
        )
    writer = "for i in range(6):\n    s.create({'type': 'Concept', 'title': f'Worker {sys.argv[2]} note {i}'}, 'A local finding.', 'process:test', 'Keep a finding.')\n"
    reader = "from memora.index import Index\nfor i in range(12):\n    index = Index(s)\n    try:\n        index.refresh()\n        index.all()\n    finally:\n        index.close()\n    time.sleep(0.01)\n"
    children = [process(store, writer, i) for i in range(4)] + [process(store, reader)]
    try:
        for child in children:
            output = child.communicate(timeout=30)
            assert child.returncode == 0, output
    finally:
        for child in children:
            finish(child)
    from memora.knowledge import notes

    assert len(list(notes(store))) == 24
    assert len(store.events()) == 24
    if legacy:
        assert len(list((store.cache / "legacy-locks").iterdir())) == 1
    index = Index(store)
    try:
        index.refresh()
        assert len(index.all()) == 24
    finally:
        index.close()


def test_competing_updates_accept_exactly_one_expected_revision(store, note):
    script = "from memora.codec import Conflict\ntry:\n    s.update(sys.argv[2], {}, 'A new claim.', 'process:test', 'Update the claim.', 1)\n    print('saved')\nexcept Conflict:\n    print('conflict')\n"
    children = [process(store, script, note["path"]) for _ in range(5)]
    try:
        results = [child.communicate(timeout=20) for child in children]
        assert all(child.returncode == 0 for child in children), results
        assert [out.strip() for out, _ in results].count("saved") == 1
        assert [out.strip() for out, _ in results].count("conflict") == 4
    finally:
        for child in children:
            finish(child)
    assert len(store.events(note["path"])) == 2
    assert store.read(note["path"])[0]["brain"]["revision"] == 2


def test_process_crash_recovers_the_pending_transaction_on_next_read(store, note):
    child = process(
        store,
        "import os\noriginal = s.recover\ncalls = 0\ndef interrupted():\n    global calls\n    calls += 1\n    if calls == 2:\n        os._exit(77)\n    original()\ns.recover = interrupted\ns.update(sys.argv[2], {}, 'Recovered claim.', 'process:test', 'Keep the claim.', 1)\n",
        note["path"],
    )
    try:
        child.communicate(timeout=20)
        assert child.returncode == 77
        assert (store.cache / "transaction.json").exists()
        from memora.service import MemoryService

        result = MemoryService(store).get_note(note["path"])
        assert "Recovered claim." in result["body"]
        assert store.read(note["path"])[0]["brain"]["revision"] == 2
        assert len(store.events(note["path"])) == 2
        assert not (store.cache / "transaction.json").exists()
    finally:
        finish(child)


def test_legacy_dead_owner_is_archived_and_migrated(store):
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait(timeout=10)
    lock = store.cache / "write.lock"
    lock.mkdir()
    (lock / "owner.json").write_text(json.dumps({"pid": child.pid}))
    # Use a PID that the OS confirms absent, rather than treating a timestamp as proof.
    with store.lock(timeout=0.5):
        pass
    assert lock.is_file()
    assert len(list((store.cache / "legacy-locks").glob("*/owner.json"))) == 1


@pytest.mark.parametrize("owner", [None, {"pid": "invalid"}, {"pid": os.getpid()}])
def test_legacy_unknown_or_active_owner_is_not_removed(store, owner):
    lock = store.cache / "write.lock"
    lock.mkdir()
    if owner:
        (lock / "owner.json").write_text(json.dumps(owner))
    with pytest.raises(Conflict, match="legacy|Legacy"), store.lock(timeout=0.03):
        pytest.fail("An unverified legacy owner must not be removed.")
    assert lock.is_dir()


def test_doctor_clear_option_keeps_the_kernel_lock_inode(store, tmp_path):
    with store.lock():
        pass
    inode = (store.cache / "write.lock").stat().st_ino
    args = parser().parse_args(
        [
            "--root",
            str(store.root),
            "--home",
            str(tmp_path),
            "doctor",
            "--clear-dead-lock",
        ]
    )
    assert run(args)["write_lock"] is False
    assert (store.cache / "write.lock").stat().st_ino == inode


def test_diagnostic_distinguishes_a_persistent_file_from_current_ownership(store):
    assert is_locked(store.cache) is False
    with store.lock():
        assert is_locked(store.cache) is True
    assert (store.cache / "write.lock").is_file()
    assert is_locked(store.cache) is False


def test_doctor_clear_cannot_remove_an_active_kernel_lock(store, tmp_path, monkeypatch):
    child = process(
        store,
        "with s.lock():\n    (s.cache / 'ready').write_text('ready')\n    time.sleep(60)\n",
    )
    original = Store.lock
    try:
        ready(child, store.cache / "ready")
        monkeypatch.setattr(Store, "lock", lambda self: original(self, timeout=0.03))
        args = parser().parse_args(
            [
                "--root",
                str(store.root),
                "--home",
                str(tmp_path),
                "doctor",
                "--clear-dead-lock",
            ]
        )
        with pytest.raises(Conflict, match="busy"):
            run(args)
        assert (store.cache / "write.lock").is_file()
    finally:
        finish(child)


def test_legacy_process_probe_permission_denial_never_proves_a_dead_owner(
    store, monkeypatch
):
    lock = store.cache / "write.lock"
    lock.mkdir()
    (lock / "owner.json").write_text(json.dumps({"pid": 123}))

    def denied(_pid, _signal):
        raise PermissionError("The owner is outside the client sandbox.")

    monkeypatch.setattr(os, "kill", denied)
    with pytest.raises(Conflict, match="active"), store.lock(timeout=0.03):
        pass
    assert lock.is_dir()


def _fork_contender(root, connection):
    store = Store(Path(root))
    try:
        with store.lock(timeout=0.05):
            connection.send("unsafe")
    except Conflict:
        connection.send("blocked")
    connection.recv()
    with store.lock(timeout=2):
        connection.send("acquired")
    connection.close()


@pytest.mark.skipif(
    not hasattr(os, "fork"), reason="Fork behavior is specific to POSIX."
)
def test_forked_child_does_not_inherit_reentrant_ownership_or_unlock_parent(store):
    context = multiprocessing.get_context("fork")
    parent, child = context.Pipe()
    process = context.Process(target=_fork_contender, args=(str(store.root), child))
    try:
        with store.lock():
            process.start()
            assert parent.poll(10)
            assert parent.recv() == "blocked"
        parent.send("continue")
        assert parent.poll(10)
        assert parent.recv() == "acquired"
        process.join(timeout=10)
        assert process.exitcode == 0
    finally:
        if process.is_alive():
            process.kill()
            process.join(timeout=10)
        parent.close()
        child.close()


def test_lock_symlink_and_invalid_timeout_fail_without_external_changes(
    store, tmp_path
):
    for timeout in (-1, float("nan"), float("inf")):
        with pytest.raises(MemoraError, match="timeout"), store.lock(timeout=timeout):
            pass
    external = tmp_path / "external"
    external.write_text("Keep this file.")
    (store.cache / "write.lock").symlink_to(external)
    with pytest.raises(MemoraError, match="symbolic"), store.lock():
        pass
    assert external.read_text() == "Keep this file."
