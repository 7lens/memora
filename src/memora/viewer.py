"""Build graph data for the live memory viewer."""

from __future__ import annotations

import hashlib
import json
from importlib.resources import files
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .codec import now
from .index import Index


def version(index: Index) -> str:
    rows = index.db.execute("SELECT path, stamp FROM nodes ORDER BY path")
    content = "\n".join(f"{row['path']}\0{row['stamp']}" for row in rows)
    for path in sorted((index.store.cache / "sessions").glob("*.json")):
        content += path.name + path.read_text()
    return hashlib.sha256(content.encode()).hexdigest()


def data(index: Index, live: bool = False) -> dict:
    from .sessions import list_sessions

    nodes = index.all()
    config_file = index.store.cache / "config.json"
    config = json.loads(config_file.read_text()) if config_file.exists() else {}
    repositories = config.get("repositories", {})
    for n in nodes:
        path = index.store.path(n["path"])
        n["file"] = path.as_uri()
        for source in n["sources"]:
            resource = source["resource"]
            parsed = urlsplit(resource)
            if parsed.scheme in {"http", "https"}:
                source["href"] = resource
            elif not parsed.scheme:
                candidate = (
                    index.store.bundle / unquote(resource).lstrip("/")
                ).resolve()
                if (
                    candidate.is_relative_to(index.store.bundle.resolve())
                    and candidate.is_file()
                ):
                    source["href"] = candidate.as_uri()
                    continue
                for repository in n["repositories"]:
                    record = repositories.get(repository, {})
                    repository_root = record.get("root")
                    if not repository_root:
                        continue
                    candidate = (
                        Path(repository_root) / unquote(resource).lstrip("/")
                    ).resolve()
                    root = Path(repository_root).resolve()
                    if candidate.is_relative_to(root) and candidate.is_file():
                        source["href"] = candidate.as_uri()
                        break
        n["history_file"] = (
            index.store.path(n["last_event"]).as_uri() if n.get("last_event") else None
        )
        if len(n["description"]) > 500:
            n["description"] = n["description"][:497] + "..."
    edges = [
        {
            "origin": n["path"],
            "target": e["target"],
            "kind": e["type"],
            **({"id": e["id"]} if e.get("id") else {}),
        }
        for n in nodes
        for e in n["relations"]
    ]
    relations = {e["id"]: e for e in edges if e.get("id")}
    observed_relations = {
        e["target"].removeprefix("relation:")
        for e in edges
        if e["target"].startswith("relation:")
    }
    for identity in observed_relations:
        edge = relations.get(identity)
        if not edge:
            continue
        origin = next(n for n in nodes if n["path"] == edge["origin"])
        target = next((n for n in nodes if n["path"] == edge["target"]), None)
        nodes.append(
            {
                **origin,
                "path": "relation:" + identity,
                "id": None,
                "type": "Relation",
                "title": origin["title"]
                + " → "
                + edge["kind"]
                + " → "
                + (target["title"] if target else edge["target"]),
                "description": "A view of one canonical directed relation.",
                "relations": [],
                "file": None,
                "history_file": None,
                "publication": {},
                "sources": [],
            }
        )
    external = {}
    for note in list(nodes):
        for ref in note.get("external_refs", []):
            identity = {
                key: ref[key]
                for key in ("provider", "instance", "entity_type", "entity_id")
            }
            key = (
                "external:"
                + hashlib.sha256(
                    json.dumps(identity, sort_keys=True).encode()
                ).hexdigest()[:20]
            )
            if key not in external:
                external[key] = {
                    "path": key,
                    "type": "ExternalReference",
                    "title": ref["entity_type"] + " " + ref["entity_id"],
                    "description": "External reference. No connector has checked this entity.",
                    "tags": [ref["provider"], "external", "unchecked"],
                    "projects": [],
                    "repositories": [],
                    "state": "provisional",
                    "work_state": None,
                    "revision": 1,
                    "score": 25,
                    "reasons": [
                        "This link is a reference, not a verified external fact."
                    ],
                    "sources": [],
                    "file": None,
                    "history_file": None,
                    "relations": [],
                    "external_refs": [ref],
                    "context": {},
                    "last_event": None,
                }
            target = external[key]
            for field in ("projects", "repositories"):
                target[field] = list(dict.fromkeys(target[field] + note[field]))
            edges.append(
                {"origin": note["path"], "target": key, "kind": ref["relation"]}
            )
    nodes.extend(external.values())
    events = []
    # The live view shows recent event summaries. Full history stays in Markdown.
    paths = sorted(
        (index.store.bundle / "events").glob("*/*.md"),
        key=lambda p: p.stat().st_mtime_ns,
        reverse=True,
    )[:1000]
    from .codec import load

    for p in paths:
        data, _ = load(p.read_text(encoding="utf-8"))
        b = data["brain"]
        events.append(
            {
                "entity": b["entity"],
                "entity_id": b.get("entity_id"),
                "at": b["at"],
                "actor": b["actor"],
                "reason": b["reason"][:500],
                "revision": b["revision"],
                "file": p.as_uri(),
            }
        )
    return {
        "at": now(),
        "nodes": nodes,
        "edges": edges,
        "events": events,
        "sessions": list_sessions(index.store),
        "live": live,
        "version": version(index),
    }


def render_data(graph: dict) -> str:
    payload = json.dumps(graph, ensure_ascii=False)
    payload = (
        payload.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    template = files("memora").joinpath("viewer.html").read_text(encoding="utf-8")
    return template.replace("__BRAIN_DATA__", payload)
