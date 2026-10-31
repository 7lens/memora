"""Run the local vault synchronizer without a network service."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

from . import obsidian as vault
from .codec import Conflict, MemoraError, now
from .store import atomic


def add_commands(sub):
    parser = sub.add_parser(
        "obsidian", help="Read and edit memory through a live local vault."
    )
    actions = parser.add_subparsers(dest="action", required=True)
    for name in ("init", "sync", "start", "stop", "status"):
        actions.add_parser(name)
    parser = actions.add_parser("watch")
    parser.add_argument("--interval", type=float, default=1.0)
    parser = actions.add_parser("resolve")
    parser.add_argument("id", help="The Memora note UUID.")
    parser.add_argument("--keep", choices=["memory", "vault"], required=True)
    parser.add_argument("--revision", type=int, required=True)


def worker_path(store) -> Path:
    return vault.cache(store) / "worker.json"


def worker(store) -> dict:
    path = worker_path(store)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def alive(record: dict) -> bool:
    if not record.get("running") or not isinstance(record.get("pid"), int):
        return False
    try:
        os.kill(record["pid"], 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # A restricted client can lack permission to probe an existing worker.
        # The kernel file lock remains the authority for its running state.
        return True
    return True


def running(store, record: dict) -> bool:
    if not alive(record):
        return False
    try:
        import fcntl
    except ImportError:
        return False
    with (vault.cache(store) / "worker.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        return False


def status(store) -> dict:
    record = worker(store)
    state = vault.read_state(store) if vault.state_path(store).exists() else {}
    active = running(store, record)
    return {
        "path": str(vault.directory(store)),
        "initialized": bool(state),
        "running": active,
        "pid": record.get("pid") if active else None,
        "last_sync": state.get("last_sync"),
        "notes": len(state.get("entries", {})),
        "issues": state.get("issues", []),
        "error": record.get("error"),
        "log": str(vault.cache(store) / "watch.log"),
    }


def signature(store) -> tuple:
    paths = [
        store.bundle / ".memora-version.json",
        store.root / "docs/types.md",
        store.root / "docs/relations.md",
    ]
    for child in store.bundle.iterdir():
        if child.name in {"events", "catalog"}:
            continue
        paths.extend(child.rglob("*.md") if child.is_dir() else [child])
    paths.extend((vault.directory(store) / "Notes").rglob("*"))
    values = []
    for path in paths:
        try:
            stat = path.lstat()
            values.append((str(path), stat.st_mtime_ns, stat.st_size, stat.st_mode))
        except FileNotFoundError:
            continue
    return tuple(sorted(values))


def watch(store, interval: float) -> None:
    if not 0.1 <= interval <= 60:
        raise MemoraError("Use a watch interval from 0.1 to 60 seconds.")
    # The kernel releases this lock on normal exit, termination, or a process crash.
    # It also prevents two workers from accepting the same edits concurrently.
    try:
        import fcntl
    except ImportError as exc:
        raise MemoraError(
            "The background watcher requires macOS or Linux. Use obsidian sync on this system."
        ) from exc
    vault.cache(store).mkdir(parents=True, exist_ok=True)
    with (vault.cache(store) / "worker.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise Conflict(
                "The vault synchronization process is already running."
            ) from exc
        token = uuid.uuid4().hex
        record = {
            "pid": os.getpid(),
            "token": token,
            "running": True,
            "started_at": now(),
            "error": None,
        }
        stop_path = vault.cache(store) / ("stop-" + token)
        stopped = False

        def request_stop(_signum, _frame):
            nonlocal stopped
            stopped = True

        previous = {
            s: signal.signal(s, request_stop) for s in (signal.SIGTERM, signal.SIGINT)
        }
        try:
            atomic(worker_path(store), json.dumps(record))
            previous_signature = None
            while not stopped and not stop_path.exists():
                try:
                    current_signature = signature(store)
                    if current_signature != previous_signature:
                        summary = vault.synchronize(store)
                        record.update(error=None, last_sync=summary["last_sync"])
                        # Remember the input scan. A write during this cycle must
                        # trigger another pass, including our own projection writes.
                        previous_signature = current_signature
                        atomic(worker_path(store), json.dumps(record))
                except (MemoraError, OSError, ValueError, TypeError, KeyError) as exc:
                    record["error"] = str(exc)
                    print(json.dumps({"at": now(), "error": str(exc)}), flush=True)
                    atomic(worker_path(store), json.dumps(record))
                time.sleep(interval)
        finally:
            record["running"] = False
            atomic(worker_path(store), json.dumps(record))
            stop_path.unlink(missing_ok=True)
            for signum, handler in previous.items():
                signal.signal(signum, handler)


def start(store) -> dict:
    if not vault.state_path(store).exists():
        vault.initialize(store)
    if status(store)["running"]:
        return status(store)
    with (vault.cache(store) / "watch.log").open("a", encoding="utf-8") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "memora",
                "--root",
                str(store.root),
                "obsidian",
                "watch",
            ],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
            cwd=store.root,
        )
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        current = status(store)
        if current["running"]:
            return current
        if process.poll() is not None:
            break
        time.sleep(0.05)
    raise MemoraError("The watcher did not start. Read .brain/obsidian/watch.log.")


def stop(store) -> dict:
    record = worker(store)
    if running(store, record):
        atomic(
            vault.cache(store) / ("stop-" + record["token"]),
            "Stop the local watcher.\n",
        )
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and status(store)["running"]:
            time.sleep(0.05)
    return status(store)


def dispatch(store, args):
    if args.action == "init":
        return vault.initialize(store)
    if args.action == "sync":
        return vault.synchronize(store)
    if args.action == "status":
        return status(store)
    if args.action == "start":
        return start(store)
    if args.action == "stop":
        return stop(store)
    if args.action == "watch":
        if not vault.state_path(store).exists():
            vault.initialize(store)
        watch(store, args.interval)
        return None
    result = vault.synchronize(store, (args.id, args.keep, args.revision))
    if any(issue.get("id") == args.id for issue in result["issues"]):
        raise Conflict("The note still has a pending issue. Read obsidian status.")
    return result
