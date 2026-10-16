"""Store notes and immutable change events."""

from __future__ import annotations

import copy
import json
import os
import re
import subprocess
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from .codec import (
    STATES,
    RELATIONS,
    TYPES,
    MemoraError,
    Conflict,
    digest,
    dump,
    instant,
    load,
    now,
    plain,
    relations,
    render_relations,
    safe_path,
    validate_fields,
)


def atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temp.open("w", encoding="utf-8") as out:
            out.write(text)
            out.flush()
            os.fsync(out.fileno())
        os.chmod(temp, path.stat().st_mode & 0o777 if path.exists() else 0o600)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


class Store:
    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()
        self.bundle = self.root / "knowledge"
        self.cache = self.root / ".brain"
        self.bundle.mkdir(parents=True, exist_ok=True)
        self.cache.mkdir(parents=True, exist_ok=True)

    def require_ignored_memory(self) -> None:
        if not (self.root / ".git").exists():
            return
        result = subprocess.run(
            [
                "git",
                "-C",
                str(self.root),
                "check-ignore",
                "--verbose",
                "--no-index",
                "--",
                "knowledge/.memora-write-check",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        ignore_source = result.stdout.partition(":")[0]
        if result.returncode != 0 or ignore_source != ".gitignore":
            raise MemoraError(
                "Git must ignore the full knowledge directory before a memory write. "
                "Add /knowledge/ to .gitignore."
            )

    def path(self, key: str) -> Path:
        name = safe_path(key)
        path = self.bundle / name.lstrip("/")
        if not path.resolve().is_relative_to(self.bundle.resolve()):
            raise MemoraError("The path leaves the knowledge bundle.")
        return path

    @contextmanager
    def lock(self):
        lock = self.cache / "write.lock"
        deadline = time.monotonic() + 10
        while True:
            try:
                lock.mkdir()
                atomic(
                    lock / "owner.json", json.dumps({"pid": os.getpid(), "at": now()})
                )
                break
            except FileExistsError:
                if time.monotonic() > deadline:
                    raise Conflict(
                        "The memory is in use. Run doctor if the lock is old."
                    )
                time.sleep(0.02)
        try:
            self.recover()
            yield
        finally:
            (lock / "owner.json").unlink(missing_ok=True)
            lock.rmdir()

    def recover(self) -> None:
        from .bundles import recover_import

        recover_import(self)
        journal = self.cache / "transaction.json"
        if not journal.exists():
            return
        tx = json.loads(journal.read_text())
        path = self.path(tx["entity"])
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current is not None and digest(current) not in {
            tx["before_hash"],
            digest(tx["after"]),
        }:
            raise Conflict(
                "Recovery found an external change. Keep the journal for review."
            )
        event_path = self.path(tx["event_path"])
        if (
            event_path.exists()
            and event_path.read_text(encoding="utf-8") != tx["event_text"]
        ):
            raise Conflict("An event identity has different content.")
        atomic(path, tx["after"])
        if not event_path.exists():
            atomic(event_path, tx["event_text"])
        event, _ = load(tx["event_text"])
        self.write_log(event["brain"], tx["event_path"])
        journal.unlink()

    def write_log(self, event: dict, event_path: str) -> None:
        path = self.bundle / "log.md"
        current = path.read_text() if path.exists() else "# Knowledge update log\n"
        if event_path in current:
            return
        date = event["at"][:10]
        reason = event["reason"].replace("\n", " ")
        line = f"- **Update**: {event['at']} [{event['entity']}](<{event['entity']}>) - {reason} [Event](<{event_path}>).\n"
        heading = "## " + date + "\n"
        if heading in current:
            current = current.replace(heading, heading + line, 1)
        else:
            current = (
                "# Knowledge update log\n\n"
                + heading
                + line
                + "\n"
                + current.removeprefix("# Knowledge update log").lstrip()
            )
        atomic(path, current.rstrip() + "\n")

    def read(self, key: str) -> tuple[dict, str]:
        path = self.path(key)
        if not path.exists():
            raise MemoraError(f"The note does not exist: {key}")
        if path.stat().st_size > 1024 * 1024:
            raise MemoraError("The note exceeds 1 MiB. Use a source document.")
        data, body = load(path.read_text(encoding="utf-8"))
        if data["type"] != "Memory Event":
            relations(data, body, safe_path(key))
        return data, body

    def types(self) -> dict:
        path = self.root / "docs" / "types.md"
        if not path.exists():
            return {t: t for t in TYPES}
        data, _ = load(path.read_text())
        return plain(data.get("brain", {}).get("types", {}))

    def relation_types(self) -> dict:
        path = self.root / "docs" / "relations.md"
        if not path.exists():
            return {name: name for name in RELATIONS}
        data, _ = load(path.read_text(encoding="utf-8"))
        return plain(data.get("brain", {}).get("relation_types", {}))

    def commit(
        self,
        key: str,
        data: dict,
        body: str,
        actor: str,
        reason: str,
        expected: int | None = None,
    ) -> dict:
        self.require_ignored_memory()
        if len(body.encode()) > 65536:
            raise MemoraError("The note exceeds 64 KiB. Link to the source document.")
        if not actor.strip() or not reason.strip():
            raise MemoraError("Supply an actor and a reason.")
        from .compatibility import has_memory, marker_path, record_baseline

        set_initial_version = not marker_path(self).exists() and not has_memory(self)
        key = safe_path(key)
        if key.startswith("/events/"):
            raise MemoraError("Change events are immutable.")
        if data["type"] not in self.types():
            raise MemoraError("Add the new type to docs/types.md first.")
        path = self.path(key)
        before = path.read_text(encoding="utf-8") if path.exists() else None
        old_revision = 0
        old = None
        if before:
            old, old_body = load(before)
            relations(old, old_body, key)
            old_revision = old.get("brain", {}).get("revision", 1)
            if expected is None or expected != old_revision:
                raise Conflict(
                    f"The revision is {old_revision}. Supply --revision {old_revision}."
                )
        elif expected not in (None, 0):
            raise Conflict("The note does not exist at that revision.")
        from .knowledge import prepare, notes

        supplied_id = data.get("brain", {}).get("id")
        if not old and supplied_id:
            if any(
                d.get("brain", {}).get("id") == supplied_id for _, d, _ in notes(self)
            ):
                raise Conflict("This entity identity is in use.")
        prepare(self, data, old)
        stamp = now()
        b = data.setdefault("brain", {})
        b.setdefault("state", "provisional")
        b.setdefault("created_at", stamp)
        b["revision"] = old_revision + 1
        data["status"] = STATES[b["state"]]
        data["generated"] = {"by": actor, "at": stamp}
        body = render_relations(body, b.get("relations", []))
        validate_fields(data)
        publication = b.get("publication", {})
        if publication.get("state") in {"candidate", "approved"}:
            from .knowledge import fingerprint

            if publication.get("fingerprint") != fingerprint(data, body):
                publication["state"] = "stale"
        validate_fields(data)
        relations(data, body, key)
        event_id = uuid.uuid4().hex
        event_key = f"/events/{stamp[:10]}/{event_id}.md"
        b["last_event"] = event_key
        after = dump(data, body)
        if len(after.encode()) > 1024 * 1024:
            raise MemoraError("The note exceeds 1 MiB. Use a source document.")
        event = {
            "type": "Memory Event",
            "title": f"Change {event_id[:8]}",
            "generated": {"by": actor, "at": stamp},
            "brain": {
                "entity": key,
                "entity_id": b["id"],
                "actor": actor,
                "at": stamp,
                "reason": reason,
                "revision": b["revision"],
                "before": before,
                "after": after,
            },
        }
        text = dump(event, "## Change\n\n" + reason)
        tx = {
            "entity": key,
            "before_hash": digest(before) if before else None,
            "after": after,
            "event_path": event_key,
            "event_text": text,
        }
        atomic(self.cache / "transaction.json", json.dumps(tx, ensure_ascii=False))
        self.recover()
        if set_initial_version:
            record_baseline(self, actor, reason)
        return {
            "path": key,
            "id": b["id"],
            "revision": b["revision"],
            "event": event_key,
        }

    def create(
        self, data: dict, body: str, actor: str, reason: str, key: str | None = None
    ) -> dict:
        if len(body.encode()) > 65536:
            raise MemoraError("The note exceeds 64 KiB. Link to the source document.")
        slug = (
            re.sub(r"[^a-z0-9]+", "-", data.get("title", "note").lower()).strip("-")[
                :50
            ]
            or "note"
        )
        key = key or f"/nodes/{slug}-{uuid.uuid4().hex[:12]}.md"
        with self.lock():
            if self.path(key).exists():
                raise Conflict("This note identity is in use.")
            return self.commit(key, copy.deepcopy(data), body, actor, reason)

    def update(
        self,
        key: str,
        patch: dict,
        body: str | None,
        actor: str,
        reason: str,
        expected: int,
    ) -> dict:
        with self.lock():
            data, old_body = self.read(key)
            merge(data, patch)
            return self.commit(
                key, data, old_body if body is None else body, actor, reason, expected
            )

    def events(self, key: str | None = None) -> list[dict]:
        identity = None
        if key and self.path(key).exists():
            identity = self.read(key)[0].get("brain", {}).get("id")
        events = []
        for path in (self.bundle / "events").rglob("*.md"):
            data, _ = load(path.read_text(encoding="utf-8"))
            event = plain(data["brain"])
            event_identity = event.get("entity_id")
            if identity and not event_identity and event.get("after"):
                event_identity = load(event["after"])[0].get("brain", {}).get("id")
            event["path"] = "/" + path.relative_to(self.bundle).as_posix()
            events.append((event, event_identity))
        aliases = {key} | {
            e["entity"] for e, eid in events if identity and eid == identity
        }
        result = [
            e
            for e, eid in events
            if key is None
            or (eid == identity if identity and eid else e["entity"] in aliases)
        ]
        return sorted(result, key=lambda e: (instant(e["at"]), e["path"]))

    def history(self, key: str, at: str | None = None):
        events = self.events(key)
        if at:
            events = [e for e in events if instant(e["at"]) <= instant(at)]
            return events[-1]["after"] if events else None
        return [
            {k: v for k, v in e.items() if k not in {"before", "after"}} for e in events
        ]


def merge(target: dict, patch: dict) -> None:
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(target.get(k), dict):
            merge(target[k], v)
        else:
            target[k] = copy.deepcopy(v)
