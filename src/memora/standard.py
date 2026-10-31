"""Memora Knowledge Standard: validation, linked data, and portable vault views."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import tempfile
from importlib.resources import files
from pathlib import Path
from urllib.parse import quote

from jsonschema import Draft202012Validator, FormatChecker

from . import knowledge as k
from .codec import MemoraError, TYPES, RELATIONS, dump, load, plain
from .remote import seal
from .store import atomic

VERSION = "1.0.0"
FORMAT = "memora-knowledge-v1"
LOCAL_TYPES = {"Profile", "Task", "Checkpoint", "Memory Event"}
SCHEMAS = {
    "exchange": "standard.schema.json",
    "note": "note.schema.json",
    "ingestion": "ingestion.schema.json",
    "legacy-v1": "knowledge.schema.json",
    "legacy-v2": "knowledge.remote.schema.json",
}


def resource(name: str) -> dict:
    return json.loads(files("memora").joinpath(name).read_text(encoding="utf-8"))


def schema(profile: str = "exchange") -> dict:
    if profile not in SCHEMAS:
        raise MemoraError("Select a supported standard profile.")
    return resource(SCHEMAS[profile])


def validate_schema(value: object, profile: str) -> None:
    validator = Draft202012Validator(schema(profile), format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(value), key=lambda e: str(list(e.path)))
    if errors:
        error = errors[0]
        path = "/".join(str(p) for p in error.path) or "root"
        # Do not include the rejected value. A diagnostic can otherwise expose a secret.
        raise MemoraError(
            f"The {profile} profile is not valid at {path} ({error.validator})."
        )


def validate_package(value: dict) -> dict:
    if not isinstance(value, dict):
        raise MemoraError("Use a knowledge package object.")
    profile = {
        FORMAT: "exchange",
        "context-knowledge-v1": "legacy-v1",
        "context-knowledge-v2": "legacy-v2",
    }.get(value.get("format"))
    if not profile:
        raise MemoraError("The knowledge format or major version is not supported.")
    validate_schema(value, profile)
    if profile == "legacy-v1":
        from .codec import digest, json_text

        payload = {key: item for key, item in value.items() if key != "sha256"}
        checksum = digest(json_text(payload))
    else:
        checksum = seal(value)["sha256"]
    if checksum != value["sha256"]:
        raise MemoraError("The knowledge checksum does not match the content.")
    records = {record["id"]: record for record in value["records"]}
    edges = {edge["id"]: edge for edge in value["relations"]}
    if (
        len(records) != len(value["records"])
        or len(edges) != len(value["relations"])
        or records.keys() & edges.keys()
    ):
        raise MemoraError("Knowledge and relation identities must be unique.")
    for edge in edges.values():
        if (
            edge["origin"] == edge["target"]
            or edge["origin"] not in records
            or edge["target"] not in records
        ):
            raise MemoraError("Each relation needs two included, distinct endpoints.")
    for record in records.values():
        kind = record["type"]
        if kind in LOCAL_TYPES:
            raise MemoraError("Working memory cannot enter a reviewed package.")
        if kind == "Entity" and not record.get("entity_kind"):
            raise MemoraError("An Entity needs its subject kind.")
        observation = record.get("observation")
        if (kind == "Observation") != bool(observation):
            raise MemoraError("Observation content and type must agree.")
        if observation:
            k.validate(
                {
                    "type": kind,
                    "sources": record["sources"],
                    "brain": {"observation": observation},
                }
            )
            subject = observation["subject"]
            if subject["id"] not in (records if subject["kind"] == "entity" else edges):
                raise MemoraError("Include the observation subject and its endpoints.")
        if profile == "exchange":
            import re

            if kind == "Fact" and not record["sources"]:
                raise MemoraError(
                    "A standard Fact needs a source. Use an Observation for an inference."
                )
            if kind not in TYPES and not re.fullmatch(
                r"[a-z][a-z0-9_]*:[A-Z][A-Za-z0-9]*", kind
            ):
                raise MemoraError("Use a core type or a namespaced extension type.")
            if any(edge["type"] not in RELATIONS for edge in edges.values()):
                raise MemoraError(
                    "Map extension relations to the core catalog before exchange."
                )
    return {
        "valid": True,
        "profile": profile,
        "records": len(records),
        "relations": len(edges),
    }


def export_package(store, destination: str) -> dict:
    from .bundles import identity
    from .remote import read_config

    package = k.export_shared(store, destination, standard=True)
    memory_identity = identity(store)
    package.update(format=FORMAT, version=VERSION, origin=memory_identity["brain_id"])
    baselines = {
        key: item
        for remote in read_config(store).values()
        for key, item in remote.get("baselines", {}).items()
    }
    originals = {
        data["brain"]["id"]: data["brain"].get("shared_origin")
        or data["brain"].get("remote_origin")
        or {"brain": memory_identity["notes"].get(path, "").partition(":")[0]}
        for path, data, _ in k.notes(store)
    }
    for record in package["records"]:
        record["origin"]["brain"] = (
            baselines.get(record["id"], {}).get("origin")
            or originals[record["id"]].get("brain")
            or package["origin"]
        )
    package = seal(package)
    validate_package(package)
    return package


def uri(identity: str) -> str:
    return "urn:uuid:" + identity


def actor_uri(actor: str) -> str:
    return "urn:memora:actor:" + quote(actor, safe="")


def to_jsonld(package: dict) -> dict:
    validate_package(package)
    if package["format"] != FORMAT:
        raise MemoraError(
            "Convert the package to the standard profile before JSON-LD export."
        )
    manifest = {
        key: value
        for key, value in package.items()
        if key not in {"records", "relations"}
    }
    graph = [
        {
            "id": uri(package["origin"]) + "#dataset",
            "type": "memora:Dataset",
            "manifest": manifest,
        }
    ]
    for record in package["records"]:
        provenance = record.get("provenance", {})
        observation = record.get("observation", {})
        node = {
            "id": uri(record["id"]),
            "type": ["prov:Entity", "memora:" + record["type"]],
            "title": record["title"],
            "description": record["description"],
            "body": record["body"],
            "source": [source["resource"] for source in record["sources"]],
            "record": copy.deepcopy(record),
        }
        author = observation.get("author") or provenance.get("created_by")
        if author:
            node["author"] = actor_uri(author)
        if provenance.get("created_at"):
            node["created_at"] = provenance["created_at"]
        if provenance.get("valid_until"):
            # Validity is a knowledge assertion, not a PROV invalidation event.
            node["valid_until"] = provenance["valid_until"]
        if observation:
            node.update(
                subject=uri(observation["subject"]["id"]),
                predicate=observation["predicate"],
                value=observation["value"],
                basis=observation["basis"],
            )
        if record.get("external_refs"):
            node["external_ref"] = record["external_refs"]
        graph.append(node)
        review = record["review"]
        graph.append(
            {
                "id": uri(record["id"])
                + "#review-"
                + str(record["origin"]["revision"]),
                "type": ["prov:Activity", "memora:PublicationReview"],
                "reviewed_by": actor_uri(review["by"]),
                "reviewed_at": review["at"],
                "reviewed_record": node["id"],
            }
        )
    for edge in package["relations"]:
        owner = next(node for node in graph if node["id"] == uri(edge["origin"]))
        owner.setdefault(edge["type"], []).append(uri(edge["target"]))
        graph.append(
            {
                "id": uri(edge["id"]),
                "type": "memora:Relation",
                "subject": uri(edge["origin"]),
                "object": uri(edge["target"]),
                "relation_type": edge["type"],
                "record": copy.deepcopy(edge),
            }
        )
    actors = {
        node[key] for node in graph for key in ("author", "reviewed_by") if key in node
    }
    graph.extend({"id": actor, "type": "prov:Agent"} for actor in sorted(actors))
    return {**resource("standard.context.jsonld"), "@graph": graph}


def from_jsonld(document: dict) -> dict:
    if document.get("@context") != resource("standard.context.jsonld")["@context"]:
        raise MemoraError(
            "Use the pinned Memora JSON-LD context. Remote contexts are not fetched."
        )
    graph = document.get("@graph")
    if not isinstance(graph, list) or any(not isinstance(node, dict) for node in graph):
        raise MemoraError("The JSON-LD graph is not valid.")
    manifests = [node for node in graph if node.get("type") == "memora:Dataset"]
    if len(manifests) != 1 or not isinstance(manifests[0].get("manifest"), dict):
        raise MemoraError("The JSON-LD graph needs one dataset manifest.")
    package = copy.deepcopy(manifests[0]["manifest"])
    package["records"] = [
        node["record"]
        for node in graph
        if isinstance(node.get("type"), list)
        and "prov:Entity" in node["type"]
        and "record" in node
    ]
    package["relations"] = [
        node["record"]
        for node in graph
        if node.get("type") == "memora:Relation" and "record" in node
    ]
    validate_package(package)
    if to_jsonld(package) != document:
        raise MemoraError("The semantic view and its knowledge records do not match.")
    return package


def read_document(path: Path) -> dict:
    if path.stat().st_size > 64 * 1024 * 1024:
        raise MemoraError("The standard file exceeds 64 MiB.")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise MemoraError("Use a valid UTF-8 JSON document.") from exc
    if not isinstance(value, dict):
        raise MemoraError("The standard document must be an object.")
    return from_jsonld(value) if "@graph" in value else value


def validate_file(store, path: Path) -> dict:
    if path.suffix.lower() == ".md":
        metadata, _ = load(path.read_text(encoding="utf-8"))
        validate_schema(plain(metadata), "note")
        return {"valid": True, "profile": "note"}
    value = read_document(path)
    if value.get("format") in {"memora-private-v1", "agent-brain-private-v1"}:
        from .bundles import validate_bundle

        validate_bundle(store, value)
        return {"valid": True, "profile": "private", "records": len(value["notes"])}
    return validate_package(value)


def import_document(store, path: Path) -> dict:
    value = read_document(path)
    if value.get("format") in {"memora-private-v1", "agent-brain-private-v1"}:
        from .bundles import import_bundle

        return import_bundle(store, path)
    validate_package(value)
    # The v1 import service preserves origin fields and performs one journaled batch.
    from .codec import digest, json_text

    value = copy.deepcopy(value)
    value.pop("version", None)
    value.pop("origin", None)
    value["format"] = "context-knowledge-v1"
    value.pop("sha256", None)
    value["sha256"] = digest(json_text(value))
    with tempfile.TemporaryDirectory(prefix="memora-standard-") as temp:
        source = Path(temp) / "import.json"
        source.write_text(json_text(value), encoding="utf-8")
        return k.import_shared(store, source)


def write_file(store, output: Path, value: dict) -> dict:
    output = output.expanduser().absolute()
    if (
        output.exists()
        or output.is_symlink()
        or output.resolve().is_relative_to(store.root)
    ):
        raise MemoraError("Use a new output path outside the workspace.")
    atomic(output, json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    return {
        "path": str(output),
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    }


def export_vault(store, package: dict, output: Path) -> dict:
    validate_package(package)
    return write_vault(store, package, output)


def export_private_vault(store, output: Path) -> dict:
    with store.lock():
        rows = [
            (path, data, body)
            for path, data, body in k.notes(store)
            if data["type"] not in LOCAL_TYPES
        ]
        identities = {data["brain"]["id"] for _, data, _ in rows}
        records, edges = [], []
        for _, data, body in rows:
            record = k.projection(data, body)
            record["sources"] = plain(data.get("sources", []))
            record["metadata"] = plain(data)
            record["origin"] = {
                "workspace": k.workspace(store)["id"],
                "revision": data["brain"]["revision"],
            }
            records.append(record)
            edges.extend(
                {
                    "id": e["id"],
                    "origin": data["brain"]["id"],
                    "target": e["target_id"],
                    "type": e["type"],
                }
                for e in data["brain"].get("relations", [])
                if e.get("target_id") in identities
            )
    return write_vault(
        store,
        {
            "format": "memora-private-vault-v1",
            "privacy": "private",
            "records": records,
            "relations": edges,
        },
        output,
    )


def write_vault(store, package: dict, output: Path) -> dict:
    output = output.expanduser().absolute()
    if (
        output.exists()
        or output.is_symlink()
        or output.resolve().is_relative_to(store.root)
    ):
        raise MemoraError("Use a new vault directory outside the workspace.")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".memora-vault-", dir=output.parent))
    try:
        for record in package["records"]:
            observation = record.get("observation", {})
            properties = {
                "id": record["id"],
                "type": record["type"],
                "title": record["title"],
                "description": record["description"],
                "tags": ["memora", record["type"].lower()],
                "origin_revision": record["origin"]["revision"],
                "reviewed_by": record.get("review", {}).get("by", "Not reviewed"),
            }
            for field in ("basis", "observed_at", "valid_until"):
                if field in observation:
                    properties[field] = observation[field]
            if "valid_until" in record.get("provenance", {}):
                properties["valid_until"] = record["provenance"]["valid_until"]
            links = [
                f"- {edge['type']}: [Related note]({edge['target']}.md)"
                for edge in package["relations"]
                if edge["origin"] == record["id"]
            ]
            if observation:
                subject = observation["subject"]
                target = subject["id"]
                if subject["kind"] == "relation":
                    target = next(
                        (
                            e["origin"]
                            for e in package["relations"]
                            if e["id"] == target
                        ),
                        None,
                    )
                if any(r["id"] == target for r in package["records"]):
                    links.append(f"- observes: [Subject]({target}.md)")
            # The reviewed body may itself link to local paths. The graph view uses
            # the generated ID links; the exact reviewed content stays in the manifest.
            body = record["body"] + (
                "\n\n## Relations\n\n" + "\n".join(links) if links else ""
            )
            atomic(stage / (record["id"] + ".md"), dump(properties, body))
        atomic(
            stage / "memora-export.json",
            json.dumps(package, ensure_ascii=False, indent=2),
        )
        atomic(
            stage / "README.md",
            "# Memora vault\n\nOpen this directory as an Obsidian vault.\nRead the manifest for privacy and review state.\nUse Memora to change the source and export a new vault.\nThe JSON manifest retains the exact source records.\n",
        )
        stage.rename(output)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return {
        "path": str(output),
        "records": len(package["records"]),
        "direction": "export only",
    }
