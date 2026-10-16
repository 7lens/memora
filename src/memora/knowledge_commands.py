"""CLI commands for local knowledge and reviewed exchange."""

from __future__ import annotations
import json
from pathlib import Path
from . import knowledge as k
from .codec import MemoraError, plain


def add_commands(sub):
    s = sub.add_parser(
        "workspace", help="Keep personal and team memory in separate spaces."
    )
    actions = s.add_subparsers(dest="action", required=True)
    actions.add_parser("list")
    c = actions.add_parser("create")
    c.add_argument("name")
    c.add_argument("--kind", choices=["personal", "team"], required=True)
    s = sub.add_parser(
        "entity", help="Add a person, organization, service, or other subject."
    )
    s.add_argument("--kind", required=True)
    s.add_argument("--title", required=True)
    s.add_argument("--description", required=True)
    s.add_argument("--body", default="")
    s.add_argument("--external-refs", type=Path)
    s.add_argument("--actor", default="agent:local")
    s.add_argument("--reason", required=True)
    s = sub.add_parser("observe", help="Record a dated claim and its sources.")
    s.add_argument("--subject", required=True)
    s.add_argument("--subject-kind", choices=["entity", "relation"], default="entity")
    s.add_argument("--title", required=True)
    s.add_argument("--predicate", required=True)
    s.add_argument("--value", required=True, help="A JSON value.")
    s.add_argument("--basis", choices=["direct", "reported", "inferred"], required=True)
    s.add_argument("--source", action="append", default=[])
    s.add_argument("--observed-at")
    s.add_argument("--valid-until")
    s.add_argument("--actor", default="agent:local")
    s.add_argument("--reason", required=True)
    s = sub.add_parser("relate", help="Add a typed directed relation.")
    s.add_argument("origin")
    s.add_argument("target")
    s.add_argument("--type", required=True)
    s.add_argument("--revision", type=int, required=True)
    s.add_argument("--actor", default="agent:local")
    s.add_argument("--reason", required=True)
    s = sub.add_parser(
        "migrate", help="Preview identity migration and keep a full backup on apply."
    )
    s.add_argument("--apply", action="store_true")
    s = sub.add_parser("feedback", help="Report context use without changing evidence.")
    s.add_argument("--session", required=True)
    s.add_argument("--path", required=True)
    s.add_argument(
        "--outcome", choices=["used", "corrected", "irrelevant"], required=True
    )
    s.add_argument("--reason", required=True)
    s = sub.add_parser("share", help="Propose, review, and export selected knowledge.")
    actions = s.add_subparsers(dest="action", required=True)
    for name in ["propose", "approve", "preview"]:
        c = actions.add_parser(name)
        c.add_argument("path")
        if name != "preview":
            c.add_argument("--revision", type=int, required=True)
            c.add_argument("--actor", required=True)
            c.add_argument("--reason", required=True)
        if name == "propose":
            c.add_argument("--destination", required=True)
            c.add_argument("--body", help="The exact body proposed for sharing.")
    actions.add_parser("schema")
    c = actions.add_parser("export")
    c.add_argument("--destination", required=True)

    c.add_argument("--output", type=Path, required=True)
    c = actions.add_parser("import")
    c.add_argument("file", type=Path)


def dispatch(store, args):
    command = args.command
    if command == "workspace":
        if args.action == "create":
            return k.workspace_create(store, args.name, args.kind)
        path = store.cache / "workspaces.json"
        values = json.loads(path.read_text()) if path.exists() else {}
        return [k.workspace(store)] + [
            k.workspace(k.select_workspace(store, name)) for name in values
        ]
    if command == "entity":
        return store.create(
            {
                "type": "Entity",
                "title": args.title,
                "description": args.description,
                "tags": [args.kind],
                "brain": {
                    "entity_kind": args.kind,
                    "scope": "shared",
                    "external_refs": json.loads(args.external_refs.read_text())
                    if args.external_refs
                    else [],
                },
            },
            args.body,
            args.actor,
            args.reason,
        )
    if command == "observe":
        try:
            value = json.loads(args.value)
        except ValueError as exc:
            raise MemoraError("Use a JSON observation value.") from exc
        return k.observe(
            store,
            title=args.title,
            subject=args.subject,
            subject_kind=args.subject_kind,
            predicate=args.predicate,
            value=value,
            basis=args.basis,
            sources=[{"resource": r} for r in args.source],
            actor=args.actor,
            reason=args.reason,
            observed_at=args.observed_at,
            valid_until=args.valid_until,
        )
    if command == "relate":
        return k.relate(
            store,
            args.origin,
            args.target,
            args.type,
            args.revision,
            args.actor,
            args.reason,
        )
    if command == "migrate":
        return k.migrate(store, args.apply)
    if command == "feedback":
        from .sessions import feedback

        return feedback(store, args.session, args.path, args.outcome, args.reason)
    if command == "share":
        if args.action == "schema":
            from importlib.resources import files

            return json.loads(
                files("memora").joinpath("knowledge.schema.json").read_text()
            )
        if args.action == "export":
            return k.export_shared(store, args.destination, args.output)
        if args.action == "import":
            return k.import_shared(store, args.file)
        if args.action == "propose":
            return k.propose(
                store,
                args.path,
                args.revision,
                args.destination,
                args.reason,
                args.actor,
                args.body,
            )
        if args.action == "approve":
            return k.approve(store, args.path, args.revision, args.actor, args.reason)
        return plain(
            k.find(store, args.path)[1].get("brain", {}).get("publication", {})
        )
    raise MemoraError("The knowledge command does not exist.")
