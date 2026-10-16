"""Local session receipts. These records do not prove that a model used a note."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

from .codec import MemoraError, now
from .store import atomic


def session_path(store, session_id):
    if not isinstance(session_id, str) or not re.fullmatch(
        r"[a-zA-Z0-9_-]{1,100}", session_id
    ):
        raise MemoraError("The session ID is not valid.")
    return store.cache / "sessions" / (session_id + ".json")


def read(store, session_id):
    path = session_path(store, session_id)
    if not path.exists():
        raise MemoraError("The session does not exist. Call start_task first.")
    return json.loads(path.read_text())


def record(store, session_id, kind, details):
    path = session_path(store, session_id)
    with store.lock():
        data = read(store, session_id)
        event = {"id": uuid.uuid4().hex, "at": now(), "kind": kind, **details}
        data["events"].append(event)
        data["updated_at"] = event["at"]
        atomic(path, json.dumps(data, ensure_ascii=False, indent=2))
    return event


def start(store, context, cwd: Path):
    session_id = uuid.uuid4().hex
    stamp = now()
    data = {
        "session_id": session_id,
        "created_at": stamp,
        "updated_at": stamp,
        "repository": context["repository"],
        "projects": context["projects"],
        "primary_project": context.get("primary_project"),
        "cwd": str(cwd.resolve()) if cwd is not None else None,
        "entity": context.get("entity"),
        "events": [],
    }
    with store.lock():
        atomic(session_path(store, session_id), json.dumps(data, indent=2))
    return session_id


def context_receipt(store, session_id, context):
    event = record(
        store,
        session_id,
        "context_returned",
        {
            "notes": context["notes"],
            "note_count": context["note_count"],
            "types": context["types"],
            "bytes": context["bytes"],
            "omitted_count": len(context["omitted"]),
            "requires_recheck": context["requires_recheck"],
            "search": context["search"],
            "code_revision": context["code"]["revision"],
        },
    )
    counts = (
        ", ".join(f"{count} {kind}" for kind, count in context["types"].items())
        or "no task notes"
    )
    message = (
        f"Memora returned {context['note_count']} task notes ({counts}). "
        f"{context['requires_recheck']} need a source check. "
        f"Search: {context['search']['mode']}."
    )
    selected = [
        n for n in context["notes"] if n["type"] not in {"Project", "Repository"}
    ]
    if selected:
        from .context import clip

        message += (
            " Selected: " + "; ".join(clip(n["title"], 70) for n in selected[:3]) + "."
        )
    if context["search"]["semantic"] == "unavailable":
        message += " The optional local model is unavailable. Inspect the search error."
    return {
        "session_id": session_id,
        "receipt_id": event["id"],
        "state": "context_returned",
        "message": message,
        "claim": "Tool output recorded. Client receipt and model use are not verified.",
    }


def list_sessions(store, limit=50):
    paths = sorted(
        (store.cache / "sessions").glob("*.json"),
        key=lambda p: p.stat().st_mtime_ns,
        reverse=True,
    )[:limit]
    return [json.loads(p.read_text()) for p in paths]


def status(store, session_id=None):
    sessions = [read(store, session_id)] if session_id else list_sessions(store)
    return {
        "state": "context_returned"
        if any(
            any(e["kind"] == "context_returned" for e in s["events"]) for s in sessions
        )
        else "no_context_calls",
        "sessions": sessions,
        "claim": "Recorded calls show returned context, not model understanding.",
    }


def feedback(store, session_id, path, outcome, reason):
    if outcome not in {"used", "corrected", "irrelevant"} or not reason.strip():
        raise MemoraError(
            "Use used, corrected, or irrelevant feedback and give a reason."
        )
    session = read(store, session_id)
    selected = [
        n
        for e in session["events"]
        if e["kind"] == "context_returned"
        for n in e["notes"]
        if n["path"] == path
    ]
    if not selected:
        raise MemoraError("Feedback needs a note returned in this session.")
    return record(
        store,
        session_id,
        "context_feedback",
        {
            "path": path,
            "revision": selected[-1]["revision"],
            "outcome": outcome,
            "reason": reason,
            "claim": "Agent-reported use. This feedback is not source verification.",
        },
    )
