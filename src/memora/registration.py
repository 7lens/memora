"""Project and repository registration shared by CLI and MCP."""

from __future__ import annotations
import hashlib
import json
import re
from .codec import MemoraError, Conflict
from .context import repo_identity
from .store import Store, atomic


def identity_matches(identity: dict, record: dict) -> bool:
    return bool(
        identity["common"]
        and identity["common"] == record.get("common")
        or identity["remote"]
        and identity["remote"] == record.get("remote")
        or identity["root"] == record.get("root")
    )


def registered_repository_records(store: Store, identity: dict) -> list[str]:
    config_file = store.cache / "config.json"
    config = json.loads(config_file.read_text()) if config_file.exists() else {}
    return [
        key
        for key, record in config.get("repositories", {}).items()
        if identity_matches(identity, record)
    ]


def register(store: Store, args):
    store.require_ignored_memory()
    identity = repo_identity(args.cwd)
    if args.kind == "project":
        data = {
            "type": "Project",
            "title": args.name,
            "description": args.description,
            "tags": getattr(args, "tag", []) or [args.kind],
            "sources": [{"resource": value} for value in getattr(args, "source", [])],
            "brain": {"state": "settled"},
        }
        basis = args.name
    else:
        for key in args.project:
            node, _ = store.read(key)
            if node["type"] != "Project":
                raise MemoraError("A project scope must name a Project note.")
        data = {
            "type": "Repository",
            "title": args.name,
            "description": args.description,
            "tags": getattr(args, "tag", []) or [args.kind],
            "sources": [{"resource": value} for value in getattr(args, "source", [])],
            "brain": {
                "state": "settled",
                "projects": args.project,
                "relations": [
                    {"type": "belongs_to", "target": k} for k in args.project
                ],
            },
        }
        basis = identity["remote"] or identity["common"] or identity["root"]
    slug = re.sub(r"[^a-z0-9]+", "-", args.name.lower()).strip("-")[:40] or args.kind
    collection = {"project": "projects", "repository": "repositories"}[args.kind]
    matches = (
        registered_repository_records(store, identity)
        if args.kind == "repository"
        else []
    )
    if len(matches) > 1 and not args.path:
        raise MemoraError(
            "Several repository records match. Supply --path to select one."
        )
    key = (
        args.path
        or (matches[0] if matches else None)
        or (
            f"/{collection}/{slug}-{hashlib.sha256(basis.encode()).hexdigest()[:12]}.md"
        )
    )
    if store.path(key).exists():
        current, _ = store.read(key)
        if current["type"] != data["type"]:
            raise Conflict("The registered identity has another type.")
        result = {
            "path": key,
            "revision": current.get("brain", {}).get("revision", 1),
            "existing": True,
        }
    else:
        result = store.create(
            data, "", args.actor, "Register the " + args.kind + ".", key
        )
    if args.kind == "repository":
        with store.lock():
            config_file = store.cache / "config.json"
            config = json.loads(config_file.read_text()) if config_file.exists() else {}
            config.setdefault("repositories", {})[key] = identity
            atomic(config_file, json.dumps(config, indent=2))
    return result
