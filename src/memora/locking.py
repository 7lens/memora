"""Process and thread exclusion with kernel-managed lifetime."""

from __future__ import annotations

import errno
import json
import math
import os
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from .codec import Conflict, MemoraError


@dataclass
class _LocalLock:
    mutex: threading.RLock = field(default_factory=threading.RLock)
    fd: int | None = None
    depth: int = 0


_registry: dict[str, _LocalLock] = {}
_registry_mutex = threading.Lock()


def _after_fork() -> None:
    global _registry, _registry_mutex
    # Close inherited references without LOCK_UN: the parent's descriptor still
    # owns the same open file description. Children must acquire their own lock.
    for state in _registry.values():
        if state.fd is not None:
            try:
                os.close(state.fd)
            except OSError:
                pass
    _registry = {}
    _registry_mutex = threading.Lock()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_after_fork)


def _try_lock(fd: int) -> bool:
    try:
        if os.name == "nt":
            import msvcrt

            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError as exc:
        if exc.errno in {errno.EACCES, errno.EAGAIN, errno.EINTR, errno.EDEADLK}:
            return False
        raise


def _unlock(fd: int) -> None:
    if os.name == "nt":
        import msvcrt

        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_UN)


def _open(path: Path) -> int:
    if path.is_symlink():
        raise MemoraError("The memory lock must not be a symbolic link.")
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    return os.open(path, flags, 0o600)


def _wait(fd: int, deadline: float) -> None:
    while not _try_lock(fd):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise Conflict(
                "The memory lock is busy. Retry after the active operation finishes."
            )
        time.sleep(min(0.02, remaining))


def _legacy_owner_alive(path: Path) -> bool:
    try:
        owner = json.loads((path / "owner.json").read_text(encoding="utf-8"))
        pid = owner["pid"]
        if type(pid) is not int or pid <= 0:
            raise ValueError("Invalid PID")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise Conflict(
            "A legacy lock has no valid owner record. Stop old Memora clients and review .brain/write.lock before migration."
        ) from exc
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _migrate_legacy(path: Path, deadline: float) -> None:
    # A separate, permanent kernel lock serializes migration. Never rename or
    # unlink the new write.lock inode after another process has opened it.
    fd = _open(path.parent / "lock-migration.lock")
    try:
        _wait(fd, deadline)
        if not path.is_dir():
            return
        try:
            active = _legacy_owner_alive(path)
        except Conflict:
            if not path.exists():
                return
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise
            time.sleep(min(0.02, remaining))
            return
        if active:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise Conflict(
                    "A legacy Memora lock owner is still active. Stop the old client before upgrading."
                )
            time.sleep(min(0.02, remaining))
            return
        archive = path.parent / "legacy-locks" / uuid.uuid4().hex
        archive.parent.mkdir(parents=True, exist_ok=True)
        path.rename(archive)
    finally:
        # Closing also releases the migration lock after an exception.
        os.close(fd)


def _open_memory(path: Path, deadline: float) -> int:
    while True:
        try:
            return _open(path)
        except OSError:
            if not path.is_dir():
                raise
            _migrate_legacy(path, deadline)


@contextmanager
def memory_lock(cache: Path, timeout: float = 10.0):
    """Yield True for the outer acquisition and False for a nested one."""
    if not math.isfinite(timeout) or timeout < 0:
        raise MemoraError("The lock timeout must be a finite non-negative number.")
    deadline = time.monotonic() + timeout
    acquired_pid = os.getpid()
    path = cache / "write.lock"
    with _registry_mutex:
        state = _registry.setdefault(str(path), _LocalLock())
    if not state.mutex.acquire(timeout=max(0, deadline - time.monotonic())):
        raise Conflict(
            "The memory lock is busy in another thread. Retry after the active operation finishes."
        )
    try:
        outer = state.depth == 0
        if outer:
            state.fd = _open_memory(path, deadline)
            try:
                _wait(state.fd, deadline)
            except BaseException:
                os.close(state.fd)
                state.fd = None
                raise
        state.depth += 1
        try:
            yield outer
        finally:
            if acquired_pid == os.getpid():
                state.depth -= 1
                if outer and state.fd is not None:
                    fd, state.fd = state.fd, None
                    try:
                        _unlock(fd)
                    finally:
                        os.close(fd)
    finally:
        if acquired_pid == os.getpid():
            state.mutex.release()


def is_locked(cache: Path) -> bool:
    """Report current ownership, rather than the persistent file's presence."""
    path = cache / "write.lock"
    if not path.exists():
        return False
    with _registry_mutex:
        state = _registry.get(str(path))
    if state is not None and state.depth:
        return True
    try:
        with memory_lock(cache, timeout=0):
            return False
    except Conflict:
        return True
