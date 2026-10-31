# Memory lock and recovery

Memora 1.6.1 uses a kernel file lock for local memory operations.
macOS and Linux use `fcntl.flock`. Windows uses `msvcrt.locking` on one byte.
Threads in one process also use a recursive mutex for each workspace.
Nested operations in the same thread keep the outer lock. Other threads and processes must wait.
Forked children discard inherited ownership and must acquire their own lock.

The kernel releases ownership when the process closes its descriptor or stops, including a forced termination.
An exception during owner metadata, recovery, or an operation also releases ownership.
The persistent `.brain/write.lock` file is a coordination point. Its presence is normal.
Do not delete or replace it to clear a lock. Two different file identities can permit concurrent writers.
The separate `.brain/write-owner.json` file holds diagnostic metadata. Its PID does not grant ownership.

## Busy operations

The default acquisition timeout is 10 seconds across thread and process waits.
An active long operation can still produce a busy response. Retry after that operation finishes.
The store API accepts a finite non-negative timeout for a caller that needs a shorter wait.
This timeout limits lock acquisition. It does not cancel a running write or impose a filesystem I/O deadline.

The index refresh, CLI, local viewer, ingestion, and Obsidian adapter use the same store lock.
Reads that require transaction recovery also use it. A direct note read uses the atomic Markdown file.
Independent workspaces have independent locks.

## Upgrade from directory locks

Stop the Obsidian worker and other long-running Memora clients before you update the installed package:

```sh
memora obsidian stop
.venv/bin/pip install --no-deps .
memora version
memora doctor
memora obsidian start
```

Restart editor MCP processes with the installed version. Old clients cannot acquire the new persistent lock file.
The memory format stays compatible. You need no reconsolidation.

A legacy `.brain/write.lock/` directory can remain after an older process stops.
The migration checks its owner with the operating system. If that owner no longer exists, it archives the directory under `.brain/legacy-locks/`.
A separate kernel lock serializes competing migrations. The next acquisition creates the persistent lock file.
An active owner, permission denial, or missing or invalid owner metadata does not prove a dead owner.
Those cases stop migration and retain the original directory for review. Do not remove it while an old process can still write.

## Recovery

Run `memora doctor` to acquire the lock and recover a pending transaction.
Its `write_lock` result reports current ownership, not the presence of the persistent file.
The old `--clear-dead-lock` spelling remains compatible. It uses the same safe acquisition and never removes an active kernel lock.
If a pending transaction conflicts with an external note edit, recovery stops and retains both the journal and external content.
That response needs a content review. It is separate from a stale lock.

The lock coordinates cooperating processes on a local filesystem.
It does not protect against arbitrary external file replacement, storage failure, or unsupported filesystem locking behavior.
Obsidian edits use a separate revision and file comparison boundary before they enter the store.
Tests can establish the checked behavior; they cannot prove that every future operation will avoid all failures.

Python documents the [POSIX lock interface](https://docs.python.org/3/library/fcntl.html#fcntl.flock),
[Windows byte locks](https://docs.python.org/3/library/msvcrt.html#msvcrt.locking), and
[fork callbacks](https://docs.python.org/3/library/os.html#os.register_at_fork).
