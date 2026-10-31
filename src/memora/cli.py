"""Commands for the shared agent memory."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import tomllib
import tempfile
from pathlib import Path

from .codec import (
    STATES,
    WORK_STATES,
    MemoraError,
    Conflict,
    content_hash,
    dump,
    load,
    now,
    plain,
    safe_path,
)
from .context import packet, build_packet, repo_identity
from .registration import register, identity_matches
from .compatibility import (
    assert_context_ready,
    record_reconciliation,
    status as version_status,
)
from .index import Index
from .integrations import doctor, install, uninstall
from .language import check
from .store import Store


def parser():
    p = argparse.ArgumentParser(
        prog="memora", description="Read and save the shared memory."
    )
    from . import __version__

    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("--root", type=Path, help="The memora repository.")
    p.add_argument(
        "--home",
        type=Path,
        default=Path.home(),
        help="The instruction file home directory.",
    )
    p.add_argument("--workspace", default="personal", help="The local memory space.")
    sub = p.add_subparsers(dest="command", required=True)
    from .knowledge_commands import add_commands

    add_commands(sub)
    from .remote import add_commands as add_remote_commands

    add_remote_commands(sub)
    from .standard_commands import add_commands as add_standard_commands

    add_standard_commands(sub)
    from .obsidian_commands import add_commands as add_obsidian_commands

    add_obsidian_commands(sub)

    def common(s):
        s.add_argument("--actor", default="process:memora")
        s.add_argument("--reason", required=True)

    def identity(s):
        s.add_argument("path")
        s.add_argument("--revision", type=int, required=True)
        common(s)

    def scope(s):
        s.add_argument("--project", action="append", default=[])
        s.add_argument("--repository", action="append", default=[])
        s.add_argument("--tag", action="append", default=[])

    s = sub.add_parser("register", help="Add a project or repository.")
    s.add_argument("kind", choices=["project", "repository"])
    s.add_argument("--name", required=True)
    s.add_argument("--description", default="")
    s.add_argument("--cwd", type=Path, default=Path.cwd())
    s.add_argument("--project", action="append", default=[])
    s.add_argument("--tag", action="append", default=[])
    s.add_argument("--source", action="append", default=[])
    s.add_argument("--path")
    s.add_argument("--actor", default="process:memora")
    s = sub.add_parser("capture", help="Add a knowledge note.")
    s.add_argument("--type", required=True)
    s.add_argument("--title", required=True)
    s.add_argument("--description", required=True)
    s.add_argument("--body-file", type=Path)
    s.add_argument("--body", default="")
    s.add_argument("--metadata", type=Path, help="A JSON file with extra frontmatter.")
    s.add_argument("--source", action="append", default=[])
    s.add_argument(
        "--relation", action="append", default=[], help="type:/target/path.md"
    )
    s.add_argument("--state", choices=list(STATES))
    s.add_argument("--work-state", choices=list(WORK_STATES))
    s.add_argument("--path")
    s.add_argument("--code-cwd", type=Path)
    s.add_argument("--scope", choices=["shared", "pending"])
    scope(s)
    common(s)
    s = sub.add_parser("update", help="Change a note at a known revision.")
    identity(s)
    s.add_argument("--patch", type=Path, required=True, help="A JSON merge patch.")
    s.add_argument("--body-file", type=Path)
    s = sub.add_parser("transition", help="Change a knowledge or work state.")
    identity(s)
    s.add_argument("--state", choices=list(STATES))
    s.add_argument("--work-state", choices=list(WORK_STATES))
    s = sub.add_parser(
        "verify", help="Record a source check or explicit user confirmation."
    )
    identity(s)
    s.add_argument("--evidence", type=Path)
    s.add_argument("--independent", action="store_true")
    s = sub.add_parser("show", help="Read a note.")
    s.add_argument("path")
    s.add_argument("--json", action="store_true")
    s.add_argument("--session")
    s = sub.add_parser("search", help="Find matching notes.")
    s.add_argument("query")
    s.add_argument("--limit", type=int, default=50)
    s = sub.add_parser("neighbors", help="Read relations in both directions.")
    s.add_argument("path")
    s.add_argument("--limit", type=int, default=100)
    s = sub.add_parser("context", help="Load a small task context.")
    s.add_argument("--query", default="")
    s.add_argument("--cwd", type=Path, default=Path.cwd())
    s.add_argument("--repository")
    s.add_argument("--project")
    s.add_argument("--session")
    s.add_argument("--max-bytes", type=int, default=12000)
    s.add_argument("--json", action="store_true")
    s = sub.add_parser("checkpoint", help="Save the current task progress.")
    s.add_argument("--session", required=True)
    s.add_argument("--repository")
    s.add_argument("--goal", required=True)
    s.add_argument("--progress", required=True)
    s.add_argument("--next", required=True)
    s.add_argument("--block", default="None.")
    s.add_argument(
        "--candidate",
        action="append",
        default=[],
        help="A durable fact to review for consolidation.",
    )
    s.add_argument(
        "--idea",
        action="append",
        default=[],
        help="A possible future task to review later.",
    )
    s.add_argument("--revision", type=int)
    s.add_argument("--cwd", type=Path, default=Path.cwd())
    common(s)
    s = sub.add_parser("history", help="Read changes or a previous note.")
    s.add_argument("path")
    s.add_argument("--at")
    sub.add_parser("health", help="List notes and links that need review.")
    sub.add_parser("validate", help="Validate notes, catalogs, and links.")
    sub.add_parser("reindex", help="Build the search index from Markdown.")
    sub.add_parser("version", help="Check tool and memory compatibility.")
    s = sub.add_parser("reconcile", help="Record a completed major memory migration.")
    common(s)
    s = sub.add_parser("doctor", help="Inspect access and editor pointers.")
    s.add_argument("--clear-dead-lock", action="store_true")
    s.add_argument("--probe", action="store_true")
    s = sub.add_parser("language", help="Inspect STE language issues.")
    ls = s.add_subparsers(dest="action", required=True)
    s = ls.add_parser("check")
    s.add_argument("file", type=Path)
    s.add_argument("--procedure", action="store_true")
    s.add_argument("--dictionary", type=Path)
    s.add_argument("--standard", type=Path)
    for name in ("install", "uninstall"):
        s = sub.add_parser(name, help="Manage editor instruction pointers.")
        s.add_argument(
            "--editor",
            choices=["all", "codex", "kiro", "copilot", "copilot-local", "antigravity"],
            default="all",
        )
        if name == "install":
            s.add_argument("--dry-run", action="store_true")
            s.add_argument("--transport", choices=["cli", "mcp"], default="cli")
    sub.add_parser("mcp", help="Run the local stdio MCP server.")
    s = sub.add_parser("start", help="Return context and start a task session.")
    s.add_argument("--task", required=True)
    s.add_argument("--cwd", type=Path)
    s.add_argument("--entity")
    s.add_argument("--repository")
    s.add_argument("--project")
    s.add_argument("--max-bytes", type=int, default=12000)
    s = sub.add_parser("recall", help="Refresh context for a session.")
    s.add_argument("--session", required=True)
    s.add_argument("--task", required=True)
    s.add_argument("--max-bytes", type=int, default=12000)
    s = sub.add_parser("status", help="Show real session calls.")
    s.add_argument("--session")
    s = sub.add_parser("remember", help="Save useful private knowledge for a session.")
    s.add_argument("--session", required=True)
    s.add_argument("--type", required=True)
    s.add_argument("--title", required=True)
    s.add_argument("--description", required=True)
    s.add_argument("--body", default="")
    s.add_argument("--body-file", type=Path)
    s.add_argument("--source", action="append", default=[])
    s.add_argument("--tag", action="append", default=[])
    s.add_argument("--path")
    s.add_argument("--revision", type=int)
    s.add_argument("--external-refs", type=Path)
    s.add_argument("--reason", required=True)
    s = sub.add_parser("bundle", help="Export or import private memory.")
    actions = s.add_subparsers(dest="action", required=True)
    for name in ("export", "import"):
        action = actions.add_parser(name)
        action.add_argument("file", type=Path)
    s = sub.add_parser("semantic", help="Manage the optional local search model.")
    actions = s.add_subparsers(dest="action", required=True)
    action = actions.add_parser("enable")
    action.add_argument("--revision")
    actions.add_parser("disable")
    actions.add_parser("status")
    s = sub.add_parser("view", help="Open a live view of the local memory.")
    s.add_argument("--no-open", action="store_true")
    return p


def root_path(args):
    if args.root:
        return args.root
    if os.environ.get("MEMORA_ROOT"):
        return Path(os.environ["MEMORA_ROOT"])
    for folder in [Path.cwd(), *Path.cwd().parents]:
        manifest = folder / "pyproject.toml"
        if manifest.is_file() and (folder / "START.md").is_file():
            try:
                if (
                    tomllib.loads(manifest.read_text()).get("project", {}).get("name")
                    == "memora"
                ):
                    return folder
            except tomllib.TOMLDecodeError:
                pass
    config = args.home / ".config/memora/config.json"
    if config.exists():
        return Path(json.loads(config.read_text())["root"])
    candidate = Path(__file__).resolve().parents[2]
    if (candidate / "START.md").exists():
        return candidate
    return args.home / ".local/share/memora"


def read_json(path: Path):
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise MemoraError("The JSON input must be a mapping.")
    return result


def section_body(text: str, title: str) -> str:
    match = re.search(
        rf"^## {re.escape(title)}\s*$\n(.*?)(?=^## |\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    return match.group(1).strip() if match else ""


def registered_repository_for(
    store: Store, cwd: Path, scoped: list[str]
) -> tuple[str, dict]:
    identity = repo_identity(cwd)
    config_file = store.cache / "config.json"
    config = json.loads(config_file.read_text()) if config_file.exists() else {}
    matches = []
    for key, record in config.get("repositories", {}).items():
        if identity_matches(identity, record):
            matches.append(key)
    matches = list(dict.fromkeys(matches))
    if len(matches) > 1:
        selected = [key for key in scoped if key in matches]
        if len(selected) != 1:
            raise MemoraError(
                "Several repository records match. Supply one --repository."
            )
        matches = selected
    if not matches:
        raise MemoraError("Register this repository before capturing a code finding.")
    if scoped and matches[0] not in scoped:
        raise MemoraError(
            "The code repository does not match the selected repository scope."
        )
    if not identity["revision"]:
        raise MemoraError("The code directory has no Git revision.")
    return matches[0], identity


def verify(store: Store, args):
    store.require_ignored_memory()
    if not args.actor.startswith("human:") and args.evidence is None:
        raise MemoraError("An agent source check needs an evidence file.")
    if args.independent and not args.evidence:
        raise MemoraError("An independent check needs an evidence file.")
    data, body = store.read(args.path)
    evidence = None
    if args.evidence:
        raw = args.evidence.read_bytes()
        if len(raw) > 2 * 1024 * 1024:
            raise MemoraError("The evidence file exceeds 2 MiB.")
        sha = hashlib.sha256(raw).hexdigest()
        resource = f"/references/artifacts/{sha}.txt"
        destination = store.bundle / resource.lstrip("/")
        if not destination.resolve().is_relative_to(store.bundle.resolve()):
            raise MemoraError("The evidence path leaves the knowledge bundle.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and destination.read_bytes() != raw:
            raise Conflict("The evidence identity has different content.")
        if not destination.exists():
            # This source excerpt retains its original bytes.
            with tempfile.NamedTemporaryFile(
                dir=destination.parent, delete=False
            ) as handle:
                temp = Path(handle.name)
                handle.write(raw)
            try:
                os.replace(temp, destination)
            finally:
                temp.unlink(missing_ok=True)
        evidence = {"resource": resource, "sha256": sha}
        if not data.get("sources"):
            data["sources"] = [{"resource": resource, "title": "Source check evidence"}]
    verified = plain(data.get("verified", []))
    if isinstance(verified, dict):
        verified = [verified]
    verified.append(
        {
            "by": args.actor,
            "at": now(),
            "brain": {
                "content_hash": content_hash(data, body),
                "reason": args.reason,
                "evidence": evidence,
                "independent": args.independent,
            },
        }
    )
    patch = {"verified": verified}
    if data.get("sources"):
        patch["sources"] = plain(data["sources"])
    return store.update(args.path, patch, None, args.actor, args.reason, args.revision)


def validate(store: Store):
    errors, warnings = [], []
    types = store.types()
    relation_types = store.relation_types()
    for path in store.bundle.rglob("*.md"):
        if path.name in {"index.md", "log.md"}:
            continue
        key = "/" + path.relative_to(store.bundle).as_posix()
        try:
            data, body = store.read(key)
            if data["type"] != "Memory Event" and data["type"] not in types:
                errors.append(
                    {"path": key, "message": "The type needs a catalog definition."}
                )
            if data["type"] != "Memory Event":
                from .codec import graph_relations

                tags = data.get("tags", [])
                if not any(tag.strip() for tag in tags):
                    warnings.append(
                        {
                            "path": key,
                            "message": "Add subject tags to classify this entity.",
                        }
                    )
                brain = data.get("brain", {})
                projects = brain.get("projects", [])
                repositories = brain.get("repositories", [])
                if data["type"] not in {"Project", "Repository"}:
                    if (
                        not projects
                        and not repositories
                        and brain.get("scope") != "shared"
                    ):
                        warnings.append(
                            {
                                "path": key,
                                "message": "Scope is pending. Link a project or repository, or set brain.scope to shared.",
                            }
                        )
                    if (projects or repositories) and brain.get("scope"):
                        errors.append(
                            {
                                "path": key,
                                "message": "Use project or repository links instead of a scope label.",
                            }
                        )
                seen_relations = set()
                for relation in graph_relations(data, body, key):
                    if relation.get("subject_relation_id"):
                        from .knowledge import relation as find_relation

                        find_relation(store, relation["subject_relation_id"])
                        continue
                    if relation.get("target_id"):
                        from .knowledge import find

                        target_path, _, _ = find(store, relation["target_id"])
                        relation = {**relation, "target": target_path}
                    identity = (relation["type"], relation["target"])
                    if identity in seen_relations:
                        errors.append(
                            {"path": key, "message": "A relation is repeated."}
                        )
                    seen_relations.add(identity)
                    if relation["type"] not in relation_types:
                        errors.append(
                            {
                                "path": key,
                                "message": f"Add a definition for relation type {relation['type']} to docs/relations.md.",
                            }
                        )
                    if relation["target"] == key:
                        errors.append(
                            {
                                "path": key,
                                "message": "An entity cannot relate to itself.",
                            }
                        )
                    if not store.path(relation["target"]).exists():
                        warnings.append(
                            {
                                "path": key,
                                "target": relation["target"],
                                "message": "The target does not exist.",
                            }
                        )
                    elif relation["type"] == "belongs_to":
                        target, _ = store.read(relation["target"])
                        if target["type"] not in {"Project", "Repository"}:
                            errors.append(
                                {
                                    "path": key,
                                    "message": "A belongs_to relation must target a project or repository.",
                                }
                            )
                        elif (
                            data["type"] == "Repository" and target["type"] != "Project"
                        ):
                            errors.append(
                                {
                                    "path": key,
                                    "message": "A repository can belong to a project.",
                                }
                            )
                for field, kind in [
                    ("projects", "Project"),
                    ("repositories", "Repository"),
                ]:
                    for target in data.get("brain", {}).get(field, []):
                        other, _ = store.read(target)
                        if other["type"] != kind:
                            errors.append(
                                {
                                    "path": key,
                                    "message": f"The {field} scope has another type.",
                                }
                            )
        except MemoraError as exc:
            errors.append({"path": key, "message": str(exc)})
    from .language import glossary

    glossary(store.root)
    return {"valid": not errors, "errors": errors, "warnings": warnings}


def run(args):
    from .knowledge import select_workspace

    store = select_workspace(
        Store(root_path(args)), getattr(args, "workspace", "personal")
    )
    if args.command == "obsidian":
        from .obsidian_commands import dispatch as obsidian_dispatch

        return obsidian_dispatch(store, args)
    if args.command in {"standard", "ingest", "pilot"}:
        from .standard_commands import dispatch as standard_dispatch

        return standard_dispatch(store, args)
    if args.command == "remote":
        from .remote import dispatch as remote_dispatch

        return remote_dispatch(store, args)
    if args.command in {
        "workspace",
        "entity",
        "observe",
        "relate",
        "migrate",
        "feedback",
        "share",
    }:
        from .knowledge_commands import dispatch

        return dispatch(store, args)
    if args.command == "mcp":
        try:
            from .mcp_server import run as run_mcp
        except ImportError as exc:
            raise MemoraError(
                "Install the optional mcp extra to use this transport."
            ) from exc

        run_mcp(store.root)
        return None
    if args.command in {"start", "recall", "remember"}:
        from .service import MemoryService
        from .sessions import read as read_session

        service = MemoryService(store)
        if args.command == "start":
            return service.context(
                args.task,
                args.cwd,
                repository=args.repository,
                project=args.project,
                max_bytes=args.max_bytes,
                entity=args.entity,
            )
        if args.command == "recall":
            session = read_session(store, args.session)
            return service.context(
                args.task,
                session["cwd"],
                session_id=args.session,
                max_bytes=args.max_bytes,
            )
        return service.remember(
            args.session,
            args.type,
            args.title,
            args.description,
            args.body_file.read_text() if args.body_file else args.body,
            args.reason,
            [{"resource": s} for s in args.source],
            args.tag,
            args.path,
            args.revision,
            json.loads(args.external_refs.read_text()) if args.external_refs else None,
        )
    if args.command == "status":
        from .sessions import status

        return status(store, args.session)
    if args.command == "bundle":
        from .bundles import export_bundle, import_bundle

        return (
            export_bundle(store, args.file)
            if args.action == "export"
            else import_bundle(store, args.file)
        )
    if args.command == "semantic":
        from .semantic import enable, disable, status

        if args.action == "enable":
            return enable(store, args.revision)
        return disable(store) if args.action == "disable" else status(store)
    if args.command == "version":
        return version_status(store)
    if args.command == "reconcile":
        store.require_ignored_memory()
        with store.lock():
            compatibility = version_status(store)
            if compatibility["tool_update_required"]:
                raise MemoraError(compatibility["action"])
            if compatibility["memory_status"] == "compatible":
                return {**compatibility, "reconciled": False}
            result = validate(store)
            if not result["valid"] or result["warnings"]:
                raise MemoraError(
                    "Fix every validation error and warning before reconciliation. "
                    "Run memora validate for details."
                )
            recorded = record_reconciliation(store, args.actor, args.reason)
        return {
            "reconciled": True,
            **recorded,
            "validation": result,
        }
    if args.command == "view":
        from .live import view

        if args.workspace == "personal":
            return view(store.root, args.no_open)
        return view(root_path(args), args.no_open, workspace=args.workspace)
    if args.command == "register":
        return register(store, args)
    if args.command == "capture":
        data = read_json(args.metadata) if args.metadata else {}
        if not isinstance(data.get("brain", {}), dict):
            raise MemoraError("Metadata brain must be a mapping.")
        if not isinstance(data.get("tags", []), list):
            raise MemoraError("Metadata tags must be a list.")
        if not isinstance(data.get("sources", []), list):
            raise MemoraError("Metadata sources must be a list.")
        data.update(
            {
                "type": args.type,
                "title": args.title,
                "description": args.description,
            }
        )
        b = data.setdefault("brain", {})
        data["tags"] = list(dict.fromkeys([*data.get("tags", []), *args.tag]))
        sources = [*data.get("sources", []), *({"resource": r} for r in args.source)]
        data["sources"] = list(
            {
                json.dumps(source, sort_keys=True, ensure_ascii=False): source
                for source in sources
            }.values()
        )
        for field, supplied in (
            ("projects", args.project),
            ("repositories", args.repository),
        ):
            values = b.get(field, [])
            if not isinstance(values, list) or any(
                not isinstance(value, str) for value in values
            ):
                raise MemoraError(f"Metadata {field} must be a list.")
            b[field] = list(dict.fromkeys([*values, *supplied]))
        if args.state:
            b["state"] = args.state
        else:
            b.setdefault("state", "provisional")
        scoped = bool(b.get("projects") or b.get("repositories"))
        if (args.scope or b.get("scope") == "shared") and scoped:
            raise MemoraError(
                "Set a shared or pending scope only when no project or repository is linked."
            )
        if args.scope:
            b["scope"] = args.scope
        elif scoped:
            b.pop("scope", None)
        else:
            b.setdefault("scope", "pending")
        if args.work_state:
            b["work_state"] = args.work_state
        if args.relation:
            existing_relations = b.setdefault("relations", [])
            if not isinstance(existing_relations, list) or any(
                not isinstance(relation, dict)
                or not isinstance(relation.get("type"), str)
                or not isinstance(relation.get("target"), str)
                for relation in existing_relations
            ):
                raise MemoraError(
                    "Metadata relations must contain type and target values."
                )
            for relation in args.relation:
                kind, separator, target = relation.partition(":")
                if not separator:
                    raise MemoraError("Use type:/target/path.md for a relation.")
                existing_relations.append({"type": kind, "target": target})
            b["relations"] = list(
                {
                    (relation["type"], relation["target"]): relation
                    for relation in existing_relations
                }.values()
            )
        if args.code_cwd:
            if args.scope:
                raise MemoraError("Code findings need a registered repository scope.")
            repository, ident = registered_repository_for(
                store, args.code_cwd, b.get("repositories", [])
            )
            if repository not in b["repositories"]:
                b["repositories"].append(repository)
            b.pop("scope", None)
            context = b.get("context", {})
            if not isinstance(context, dict):
                raise MemoraError("Metadata brain.context must be a mapping.")
            context.update({k: ident[k] for k in ("revision", "branch")})
            b["context"] = context
        body = (
            args.body_file.read_text(encoding="utf-8") if args.body_file else args.body
        )
        return store.create(data, body, args.actor, args.reason, args.path)
    if args.command == "update":
        return store.update(
            args.path,
            read_json(args.patch),
            args.body_file.read_text() if args.body_file else None,
            args.actor,
            args.reason,
            args.revision,
        )
    if args.command == "transition":
        if not args.state and not args.work_state:
            raise MemoraError("Supply a knowledge or work state.")
        patch = {"brain": {}}
        if args.state:
            patch["brain"]["state"] = args.state
        if args.work_state:
            patch["brain"]["work_state"] = args.work_state
        return store.update(
            args.path, patch, None, args.actor, args.reason, args.revision
        )
    if args.command == "verify":
        return verify(store, args)
    if args.command == "checkpoint":
        node = store.read(args.repository)[0] if args.repository else None
        if node and node["type"] != "Repository":
            raise MemoraError("Use a Repository note for the checkpoint.")
        key = (
            "/checkpoints/"
            + hashlib.sha256(
                ((args.repository or "workspace") + "\n" + args.session).encode()
            ).hexdigest()[:24]
            + ".md"
        )
        identity = (
            repo_identity(args.cwd)
            if args.repository
            else {"revision": None, "branch": None}
        )
        data = {
            "type": "Checkpoint",
            "tags": ["task-progress"],
            "title": "Task " + args.session,
            "description": args.goal,
            "brain": {
                "state": "provisional",
                "work_state": "in_progress",
                "repositories": [args.repository] if args.repository else [],
                "context": {
                    "session": args.session,
                    "revision": identity.get("revision"),
                    "branch": identity.get("branch"),
                },
            },
        }
        if not args.repository:
            data["brain"]["scope"] = "shared"
        sections = {
            "Goal": args.goal,
            "Progress": args.progress,
            "Block": args.block,
            "Next step": args.next,
        }
        if store.path(key).exists():
            old_metadata, old_body = store.read(key)
            data["tags"] = list(
                dict.fromkeys(old_metadata.get("tags", []) + data["tags"])
            )
            for heading in ("Memory candidates", "Ideas"):
                existing = section_body(old_body, heading)
                if existing:
                    sections[heading] = existing
        for heading, values in (
            ("Memory candidates", args.candidate),
            ("Ideas", args.idea),
        ):
            if values:
                existing = sections.get(heading, "")
                lines = [line for line in existing.splitlines() if line.strip()]
                seen = {line.removeprefix("- ").strip() for line in lines}
                for value in values:
                    value = " ".join(value.split()).removeprefix("- ").strip()
                    if value and value not in seen:
                        lines.append("- " + value)
                        seen.add(value)
                sections[heading] = "\n".join(lines)
        body = "\n\n".join(
            f"## {heading}\n\n{value}" for heading, value in sections.items()
        )
        if store.path(key).exists():
            if args.revision is None:
                raise Conflict("Supply --revision to change the checkpoint.")
            return store.update(key, data, body, args.actor, args.reason, args.revision)
        return store.create(data, body, args.actor, args.reason, key)
    if args.command == "show":
        if args.session:
            from .service import MemoryService

            note = MemoryService(store).get_note(args.path, args.session)
            data, body = note["metadata"], note["body"]
        else:
            from .knowledge import find

            _, data, body = find(store, args.path)
        return (
            {"metadata": plain(data), "body": body} if args.json else dump(data, body)
        )
    if args.command == "history":
        result = store.history(args.path, args.at)
        if args.at and result is None:
            raise MemoraError("The note did not exist at that time.")
        return result
    if args.command == "validate":
        return validate(store)
    if args.command == "language":
        text = args.file.read_text(encoding="utf-8")
        if text.startswith("---\n"):
            data, body = load(text)
            text = (
                str(data.get("title", ""))
                + "\n"
                + str(data.get("description", ""))
                + "\n"
                + body
            )
        config_file = store.cache / "config.json"
        config = json.loads(config_file.read_text()) if config_file.exists() else {}
        return check(
            text,
            store.root,
            args.procedure,
            args.dictionary
            or (Path(config["dictionary"]) if config.get("dictionary") else None),
            args.standard
            or (Path(config["standard"]) if config.get("standard") else None),
        )
    if args.command == "install":
        return install(store, args.home, args.editor, args.dry_run, args.transport)
    if args.command == "uninstall":
        return uninstall(store, args.home, args.editor)
    if args.command == "doctor":
        # Keep --clear-dead-lock as a compatible spelling. Kernel locks release
        # on process death; neither doctor variant removes the lock file.
        with store.lock():
            pass
        result = doctor(store, args.home)
        if args.probe:
            import asyncio

            try:
                from .mcp_server import probe
            except ImportError as exc:
                raise MemoraError(
                    "Install the optional mcp extra before a transport probe."
                ) from exc

            async def timed_probe():
                return await asyncio.wait_for(probe(store.root), timeout=20)

            try:
                result["mcp"] = asyncio.run(timed_probe())
            except Exception as exc:
                result["mcp"] = {"state": "connection_failed", "error": str(exc)}
                result["valid"] = False
        return result
    if args.command == "context":
        assert_context_ready(store)
    index = Index(store)
    try:
        index.refresh(force=args.command == "reindex")
        if args.command == "health":
            from .health import report

            return report(index)
        if args.command == "reindex":
            return {
                "nodes": index.db.execute("SELECT count(*) FROM nodes").fetchone()[0],
                "read_files": index.read_count,
            }
        if args.command == "search":
            if not 1 <= args.limit <= 10000:
                raise MemoraError("Use a limit from 1 to 10000.")
            return index.search(args.query, args.limit)
        if args.command == "neighbors":
            return index.neighbors(safe_path(args.path), args.limit)
        if args.command == "context":
            return (build_packet if args.json else packet)(
                index,
                args.query,
                args.cwd,
                args.repository,
                args.project,
                args.session,
                args.max_bytes,
            )
    finally:
        index.close()
    raise MemoraError("The command is not available.")


def main():
    try:
        args = parser().parse_args()
        result = run(args)
        if isinstance(result, str):
            print(result, end="" if result.endswith("\n") else "\n")
        elif result is not None:
            print(json.dumps(plain(result), ensure_ascii=False, indent=2))
        if isinstance(result, dict) and result.get("valid") is False:
            return 1
        return 0
    except Conflict as exc:
        print(json.dumps({"error": "conflict", "message": str(exc)}), file=sys.stderr)
        return 3
    except sqlite3.Error as exc:
        print(
            json.dumps({"error": "persistence_error", "message": str(exc)}),
            file=sys.stderr,
        )
        return 4
    except (MemoraError, OSError, ValueError, KeyError, TypeError) as exc:
        print(
            json.dumps({"error": "invalid_request", "message": str(exc)}),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
