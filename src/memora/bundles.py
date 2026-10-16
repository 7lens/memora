"""Private graph bundles. No network transport or remote access policy exists here."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from .codec import MemoraError, Conflict, digest, load, safe_path
from .store import atomic

FORMAT = "memora-private-v1"
LEGACY_FORMAT = "agent-brain-private-v1"


def identity(store):
    path = store.cache / "identity.json"
    if not path.exists():
        atomic(path, json.dumps({"brain_id": str(uuid.uuid4()), "notes": {}}))
    return json.loads(path.read_text())


def export_bundle(store, output: Path):
    output = output.expanduser().resolve()
    if output.is_relative_to(store.root):
        raise MemoraError("Export private memory outside the software repository.")
    if output.exists():
        raise Conflict("The output file exists. Use a new private path.")
    with store.lock():
        if output.exists():
            raise Conflict("The output file exists. Use a new private path.")
        ident = identity(store)
        notes, events = [], []
        for path in sorted(store.bundle.rglob("*.md")):
            key = "/" + path.relative_to(store.bundle).as_posix()
            if key.startswith("/catalog/") or path.name in {"index.md", "log.md"}:
                continue
            if path.is_symlink():
                raise MemoraError("A bundle cannot contain a symbolic link.")
            content = path.read_text(encoding="utf-8")
            metadata, _ = store.read(key)
            entry = {"path": key, "content": content, "sha256": digest(content)}
            if metadata["type"] == "Memory Event":
                events.append(entry)
            else:
                entry["id"] = ident["notes"].setdefault(
                    key, ident["brain_id"] + ":" + key
                )
                notes.append(entry)
        result = {
            "format": FORMAT,
            "privacy": "private",
            "brain_id": ident["brain_id"],
            "notes": notes,
            "events": events,
        }
        validate_bundle(store, result)
        atomic(store.cache / "identity.json", json.dumps(ident, indent=2))
        atomic(output, json.dumps(result, ensure_ascii=False, indent=2))
    return {
        "path": str(output),
        "notes": len(notes),
        "events": len(events),
        "privacy": "private",
    }


def validate_bundle(store, data):
    if (
        not isinstance(data, dict)
        or data.get("format") not in {FORMAT, LEGACY_FORMAT}
        or data.get("privacy") != "private"
    ):
        raise MemoraError("The private bundle format is not valid.")
    try:
        uuid.UUID(data["brain_id"])
    except (KeyError, ValueError, TypeError, AttributeError) as exc:
        raise MemoraError("The bundle identity is not valid.") from exc
    if not isinstance(data.get("notes"), list) or not isinstance(
        data.get("events"), list
    ):
        raise MemoraError("The bundle needs notes and events.")
    entries, note_ids, events = {}, set(), {}
    type_catalog = store.types()
    for field in ["notes", "events"]:
        for entry in data[field]:
            if not isinstance(entry, dict) or not isinstance(entry.get("content"), str):
                raise MemoraError("Each bundle entry needs content.")
            key = safe_path(entry.get("path", ""))
            if key != entry["path"] or key in entries or key.startswith("/catalog/"):
                raise MemoraError("The bundle has a repeated or invalid path.")
            raw = entry["content"]
            if len(raw.encode()) > 1024 * 1024 or digest(raw) != entry.get("sha256"):
                raise MemoraError("A bundle entry has an invalid size or checksum.")
            metadata, _ = load(raw)
            if field == "events":
                if not key.startswith("/events/") or metadata["type"] != "Memory Event":
                    raise MemoraError("The event path or type is not valid.")
                b = metadata["brain"]
                safe_path(b.get("entity", ""))
                if not isinstance(b.get("after"), str) or not isinstance(
                    b.get("revision"), int
                ):
                    raise MemoraError("The event snapshot is not valid.")
                snapshot, _ = load(b["after"])
                if (
                    snapshot.get("brain", {}).get("revision") != b["revision"]
                    or snapshot["brain"].get("last_event") != key
                ):
                    raise MemoraError(
                        "The event snapshot has another revision or event ID."
                    )
                events[key] = b
            else:
                if key.startswith("/events/") or metadata["type"] not in type_catalog:
                    raise MemoraError(
                        "Add the note type to docs/types.md before import."
                    )
                note_id = entry.get("id")
                if not isinstance(note_id, str) or note_id in note_ids:
                    raise MemoraError("The note identity is not valid or is repeated.")
                prefix, separator, suffix = note_id.partition(":")
                try:
                    uuid.UUID(prefix)
                except ValueError as exc:
                    raise MemoraError("The note identity is not valid.") from exc
                if not separator or safe_path(suffix) != key:
                    raise MemoraError(
                        "The note identity must use its stable bundle path."
                    )
                note_ids.add(note_id)
            entries[key] = entry
    histories = {}
    for event in events.values():
        histories.setdefault(event["entity"], []).append(event)
    for entry in data["notes"]:
        metadata, _ = load(entry["content"])
        last = metadata.get("brain", {}).get("last_event")
        if last and (
            last not in events
            or (
                events[last]["entity"] != entry["path"]
                and not (
                    metadata.get("brain", {}).get("id")
                    and load(events[last]["after"])[0].get("brain", {}).get("id")
                    == metadata["brain"]["id"]
                )
            )
            or events[last]["after"] != entry["content"]
        ):
            raise MemoraError("The note does not match its last event.")
        history = sorted(
            histories.get(entry["path"], []),
            key=lambda e: e["revision"],
        )
        for previous, current in zip(history, history[1:]):
            if (
                current["revision"] != previous["revision"] + 1
                or current.get("before") != previous["after"]
            ):
                raise MemoraError(
                    "The event history has a gap or a conflicting snapshot."
                )
    return entries


def recover_import(store):
    journal = store.cache / "import-transaction.json"
    if not journal.exists():
        return
    tx = json.loads(journal.read_text())
    for entry in tx["writes"]:
        path = store.path(entry["path"])
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if (digest(current) if current is not None else None) not in {
            entry["before_hash"],
            digest(entry["content"]),
        }:
            raise Conflict(
                "Bundle recovery found an external change. Keep the journal."
            )
    for entry in tx["writes"]:
        atomic(store.path(entry["path"]), entry["content"])
    atomic(store.cache / "identity.json", json.dumps(tx["identity"], indent=2))
    from .compatibility import marker_path, record_baseline

    if not marker_path(store).exists():
        record_baseline(store, "process:private-import", "Import private memory.")
    journal.unlink()


def import_bundle(store, source: Path):
    if source.stat().st_size > 64 * 1024 * 1024:
        raise MemoraError("The bundle exceeds 64 MiB.")
    data = json.loads(source.read_text(encoding="utf-8"))
    entries = validate_bundle(store, data)
    histories = {}
    for entry in data["events"]:
        event = load(entry["content"])[0]["brain"]
        histories.setdefault(event["entity"], []).append(event)
    store.require_ignored_memory()
    with store.lock():
        ident = identity(store)
        writes, conflicts = [], []
        for key, entry in entries.items():
            path = store.path(key)
            if path.is_symlink():
                raise MemoraError("An import target cannot be a symbolic link.")
            before = path.read_text(encoding="utf-8") if path.exists() else None
            if before == entry["content"]:
                continue
            if before is not None:
                # A newer note can advance only from a snapshot in this exact history.
                history = histories.get(key, [])
                after_meta, _ = load(entry["content"])
                before_meta, _ = load(before)
                advance = (
                    not key.startswith("/events/")
                    and after_meta["brain"].get("revision", 1)
                    > before_meta["brain"].get("revision", 1)
                    and any(
                        e["entity"] == key and e.get("before") == before
                        for e in history
                    )
                )
                if not advance:
                    conflicts.append(
                        {
                            "path": key,
                            "local_hash": digest(before),
                            "incoming_hash": entry["sha256"],
                        }
                    )
                    continue
            writes.append(
                {**entry, "before_hash": digest(before) if before is not None else None}
            )
        from .knowledge import notes

        stable_paths = {
            d.get("brain", {}).get("id"): path
            for path, d, _ in notes(store)
            if d.get("brain", {}).get("id")
        }
        for entry in data["notes"]:
            incoming_identity = load(entry["content"])[0].get("brain", {}).get("id")
            if (
                incoming_identity in stable_paths
                and stable_paths[incoming_identity] != entry["path"]
            ):
                conflicts.append(
                    {
                        "path": entry["path"],
                        "reason": "This entity identity exists at another local path.",
                    }
                )
            known = ident["notes"].get(entry["path"])
            if known is None and store.path(entry["path"]).exists():
                known = ident["brain_id"] + ":" + entry["path"]
            if known and known != entry["id"]:
                conflicts.append(
                    {
                        "path": entry["path"],
                        "reason": "Another stable note identity uses this path.",
                    }
                )
        if conflicts:
            report = store.cache / "import-conflicts" / (uuid.uuid4().hex + ".json")
            atomic(
                report,
                json.dumps(
                    {"conflicts": conflicts, "incoming": data}, ensure_ascii=False
                ),
            )
            return {
                "state": "conflict",
                "imported": 0,
                "conflicts": conflicts,
                "report": str(report),
            }
        for entry in data["notes"]:
            ident["notes"][entry["path"]] = entry["id"]
        atomic(
            store.cache / "import-transaction.json",
            json.dumps({"writes": writes, "identity": ident}, ensure_ascii=False),
        )
        recover_import(store)
    return {
        "state": "imported",
        "imported": len(writes),
        "unchanged": len(entries) - len(writes),
        "privacy": "private",
    }
