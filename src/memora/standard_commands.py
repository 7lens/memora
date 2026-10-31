"""CLI boundaries for the public standard and automatic local capture."""

from __future__ import annotations

from pathlib import Path
import json

from . import standard as s
from .codec import MemoraError


def add_commands(sub):
    standard = sub.add_parser(
        "standard", help="Validate and exchange standard knowledge."
    )
    actions = standard.add_subparsers(dest="action", required=True)
    p = actions.add_parser("schema")
    p.add_argument("--profile", choices=list(s.SCHEMAS), default="exchange")
    actions.add_parser("context")
    actions.add_parser("catalog")
    for name in ("validate", "import"):
        p = actions.add_parser(name)
        p.add_argument("file", type=Path)
    p = actions.add_parser("export")
    p.add_argument("--destination")
    p.add_argument("--private", action="store_true")
    p.add_argument("--format", choices=["json", "jsonld", "obsidian"], default="json")
    p.add_argument("--output", type=Path, required=True)
    ingest = sub.add_parser(
        "ingest", help="Save extracted conclusions as private drafts."
    )
    actions = ingest.add_subparsers(dest="action", required=True)
    p = actions.add_parser("findings")
    p.add_argument("--session", required=True)
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--preview", action="store_true")
    p = actions.add_parser("evidence")
    p.add_argument("--cwd", type=Path, required=True)
    p.add_argument("--file", required=True)
    p = sub.add_parser(
        "pilot", help="Compare real tasks with explicit private review artifacts."
    )
    actions = p.add_subparsers(dest="action", required=True)
    p = actions.add_parser("prepare")
    p.add_argument("--manifest", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--max-bytes", type=int, default=12000)
    p = actions.add_parser("run")
    p.add_argument("--directory", required=True, type=Path)
    p.add_argument("--adapter-json", required=True)
    p.add_argument("--timeout", type=int, default=180)
    p = actions.add_parser("report")
    p.add_argument("--directory", required=True, type=Path)
    p.add_argument("--ratings", type=Path)


def dispatch(store, args):
    if args.command == "pilot":
        from . import pilot

        if args.action == "prepare":
            return pilot.prepare(
                store, s.read_document(args.manifest), args.output, args.max_bytes
            )
        if args.action == "run":
            return pilot.collect(
                args.directory, json.loads(args.adapter_json), args.timeout
            )
        return pilot.report(args.directory, args.ratings)
    if args.command == "ingest":
        from .ingestion import ingest, repository_evidence

        if args.action == "evidence":
            return repository_evidence(args.cwd, args.file)
        return ingest(store, args.session, s.read_document(args.input), args.preview)
    if args.action == "schema":
        return s.schema(args.profile)
    if args.action == "context":
        return s.resource("standard.context.jsonld")
    if args.action == "catalog":
        return {
            "version": s.VERSION,
            "types": store.types(),
            "relations": store.relation_types(),
            "local_only": sorted(s.LOCAL_TYPES),
        }
    if args.action == "validate":
        return s.validate_file(store, args.file)
    if args.action == "import":
        return s.import_document(store, args.file)
    if args.private:
        if args.destination or args.format == "jsonld":
            raise MemoraError(
                "Private export accepts JSON or Obsidian without a destination. Use reviewed exchange for JSON-LD."
            )
        from .bundles import export_bundle

        if args.format == "obsidian":
            return s.export_private_vault(store, args.output)
        return export_bundle(store, args.output)
    if not args.destination:
        raise MemoraError(
            "Select the reviewed destination, or request a private JSON export."
        )
    package = s.export_package(store, args.destination)
    if args.format == "obsidian":
        return s.export_vault(store, package, args.output)
    return s.write_file(
        store, args.output, s.to_jsonld(package) if args.format == "jsonld" else package
    )
