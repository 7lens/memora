"""Stable knowledge identities, observations, and reviewed sharing."""

from __future__ import annotations

import copy
import json
import re
import shutil
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from .codec import (
    MemoraError,
    Conflict,
    content_hash,
    digest,
    instant,
    json_text,
    now,
    plain,
)
from .store import atomic


def notes(store):
    for path in sorted(store.bundle.rglob("*.md")):
        key = "/" + path.relative_to(store.bundle).as_posix()
        if key.startswith(("/events/", "/catalog/")) or path.name in {
            "index.md",
            "log.md",
        }:
            continue
        data, body = store.read(key)
        yield key, data, body


def find(store, identity):
    if isinstance(identity, str) and identity.startswith("/"):
        data, body = store.read(identity)
        return identity, data, body
    for key, data, body in notes(store):
        if data.get("brain", {}).get("id") == identity:
            return key, data, body
    raise MemoraError("The entity identity does not exist in this workspace.")


def relation(store, identity):
    for key, data, _ in notes(store):
        for edge in data.get("brain", {}).get("relations", []):
            if edge.get("id") == identity:
                return key, edge
    raise MemoraError("The relation identity does not exist in this workspace.")


def prepare(store, data, old=None):
    """Assign identities in the canonical Markdown, once per entity or edge."""
    brain = data.setdefault("brain", {})
    previous = (old or {}).get("brain", {})
    if previous.get("id") and brain.get("id", previous["id"]) != previous["id"]:
        raise MemoraError("The entity identity cannot change.")
    brain.setdefault("id", previous.get("id") or str(uuid.uuid4()))
    old_edges = {
        (e["type"], e.get("target_id") or e["target"]): e
        for e in previous.get("relations", [])
    }
    for edge in brain.get("relations", []):
        prior = old_edges.get((edge["type"], edge.get("target_id") or edge["target"]))
        if not prior:
            prior = next(
                (
                    e
                    for e in previous.get("relations", [])
                    if e["type"] == edge["type"] and e["target"] == edge["target"]
                ),
                None,
            )
        if prior and prior.get("id"):
            if edge.get("id", prior["id"]) != prior["id"]:
                raise MemoraError("The relation identity cannot change.")
            edge["id"] = prior["id"]
        edge.setdefault("id", str(uuid.uuid4()))
        if store.path(edge["target"]).exists():
            target, _ = store.read(edge["target"])
            target_id = target.get("brain", {}).get("id")
            if target_id:
                if edge.get("target_id", target_id) != target_id:
                    raise MemoraError(
                        "The relation target identity does not match its path."
                    )
                edge["target_id"] = target_id


def validate(data):
    b = data.get("brain", {})
    if "publication" in b and not isinstance(b["publication"], dict):
        raise MemoraError("Publication metadata must be a mapping.")
    for value in (
        [b.get("id")]
        + [e.get("id") for e in b.get("relations", [])]
        + [e.get("target_id") for e in b.get("relations", [])]
    ):
        if value is not None:
            try:
                uuid.UUID(value)
            except (ValueError, TypeError, AttributeError) as exc:
                raise MemoraError(
                    "Use a UUID for entity and relation identities."
                ) from exc
    if data["type"] == "Entity" and not re.fullmatch(
        r"[a-z][a-z0-9_]*", b.get("entity_kind", "")
    ):
        raise MemoraError("An Entity needs an entity_kind.")
    if data["type"] != "Observation":
        return
    obs = b.get("observation", {})
    subject = obs.get("subject", {})
    if subject.get("kind") not in {"entity", "relation"} or not isinstance(
        subject.get("id"), str
    ):
        raise MemoraError("An Observation needs an entity or relation subject.")
    try:
        uuid.UUID(subject["id"])
    except (ValueError, TypeError) as exc:
        raise MemoraError("The observation subject needs a UUID.") from exc
    if not isinstance(obs.get("predicate"), str) or not re.fullmatch(
        r"[a-z][a-z0-9_]*", obs["predicate"]
    ):
        raise MemoraError("Use a lowercase observation predicate.")
    if (
        "value" not in obs
        or not isinstance(obs.get("author"), str)
        or not obs["author"].strip()
    ):
        raise MemoraError("An Observation needs a value and an author.")
    try:
        json.dumps(plain(obs["value"]), allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise MemoraError("Use a finite JSON observation value.") from exc
    if obs.get("basis") not in {"direct", "reported", "inferred"}:
        raise MemoraError("Use a direct, reported, or inferred basis.")
    if obs["basis"] != "inferred" and not data.get("sources"):
        raise MemoraError("A direct or reported Observation needs a source.")
    observed = instant(obs.get("observed_at"))
    if obs.get("valid_until") and instant(obs["valid_until"]) <= observed:
        raise MemoraError("The validity end must follow the observation time.")


def apply_validity(data, record):
    """Project source validity into local expiry without verifying a claim."""
    ends = [
        value
        for value in (
            record.get("provenance", {}).get("valid_until"),
            record.get("observation", {}).get("valid_until"),
        )
        if value
    ]
    if ends:
        data["stale_after"] = min(ends, key=instant)
    else:
        data.pop("stale_after", None)


def observe(
    store,
    *,
    title,
    subject,
    predicate,
    value,
    basis,
    sources,
    actor,
    reason,
    observed_at=None,
    valid_until=None,
    subject_kind="entity",
    description="",
    body="",
):
    if subject_kind == "entity":
        _, node, _ = find(store, subject)
        subject = node.get("brain", {}).get("id")
    else:
        owner, _ = relation(store, subject)
        node, _ = store.read(owner)
    if not subject:
        raise MemoraError("Migrate the subject to assign a stable identity first.")
    observation = dict(
        subject={"kind": subject_kind, "id": subject},
        predicate=predicate,
        value=value,
        basis=basis,
        author=actor,
        observed_at=observed_at or now(),
    )
    if valid_until:
        observation["valid_until"] = valid_until
    data = dict(
        type="Observation",
        title=title,
        description=description or title,
        sources=sources,
        tags=["observation", predicate],
        brain=dict(observation=observation, state="provisional", scope="shared"),
    )
    scope = node.get("brain", {})
    for field in ("projects", "repositories"):
        if scope.get(field):
            data["brain"][field] = plain(scope[field])
            data["brain"].pop("scope", None)
    if valid_until:
        data["stale_after"] = valid_until
    result = store.create(data, body or title, actor, reason)
    result["sharing_candidate"] = {
        "suggested": basis != "inferred",
        "reason": "Review whether this dated source finding can help a team."
        if basis != "inferred"
        else "This inference needs evidence before it can be shared as a finding.",
    }
    return result


def relate(store, origin, target, kind, revision, actor, reason):
    key, data, _ = find(store, origin)
    target_key, target_data, _ = find(store, target)
    if key == target_key:
        raise MemoraError("An entity cannot relate to itself.")
    catalog = store.relation_types()
    if kind not in catalog:
        raise MemoraError("Add the relation type to the catalog first.")
    rule = catalog[kind]
    if isinstance(rule, dict):
        for field, node in [("origin_types", data), ("target_types", target_data)]:
            if rule.get(field) and node["type"] not in rule[field]:
                raise MemoraError(
                    "The relation endpoints do not match its catalog rule."
                )
    if kind == "belongs_to" and target_data["type"] not in {"Project", "Repository"}:
        raise MemoraError("A belongs_to relation needs a project or repository.")
    edges = plain(data.get("brain", {}).get("relations", []))
    if any(e["type"] == kind and e["target"] == target_key for e in edges):
        raise Conflict("The relation already exists.")
    edge = {"type": kind, "target": target_key}
    edges.append(edge)
    result = store.update(
        key, {"brain": {"relations": edges}}, None, actor, reason, revision
    )
    result["relation"] = plain(store.read(key)[0]["brain"]["relations"][-1])
    return result


def workspace(store):
    path = store.cache / "workspace.json"
    if path.exists():
        return json.loads(path.read_text())
    # The default space remains private. Legacy "shared" means across projects.
    return {"id": "personal", "kind": "personal", "name": "Personal"}


def workspace_create(store, name, kind):
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", name) or kind not in {
        "personal",
        "team",
    }:
        raise MemoraError("Use a short workspace name and a personal or team kind.")
    from .store import Store

    with store.lock():
        registry = store.cache / "workspaces.json"
        values = json.loads(registry.read_text()) if registry.exists() else {}
        if name == "personal" or name in values:
            raise Conflict("The workspace name exists.")
        root = store.cache / "workspaces" / name
        target = Store(root)
        value = {"id": str(uuid.uuid4()), "kind": kind, "name": name}
        atomic(target.cache / "workspace.json", json_text(value))
        if (store.root / "docs").exists():
            shutil.copytree(store.root / "docs", root / "docs", dirs_exist_ok=True)
        values[name] = str(root)
        atomic(registry, json_text(values))
    return value


def select_workspace(store, name):
    if not name or name == "personal":
        return store
    path = store.cache / "workspaces.json"
    values = json.loads(path.read_text()) if path.exists() else {}
    if name not in values:
        raise MemoraError("The workspace does not exist.")
    from .store import Store

    target = Store(Path(values[name]))
    if not target.root.is_relative_to(store.cache / "workspaces"):
        raise MemoraError("The workspace path leaves its local registry.")
    return target


def fingerprint(data, body):
    data = plain(data)
    data.pop("generated", None)
    for field in ("publication", "revision", "last_event"):
        data.get("brain", {}).pop(field, None)
    return digest(json_text(data) + "\n" + body.strip())


def projection(data, body):
    b = data["brain"]
    if data["type"] in {"Checkpoint", "Task", "Profile", "Memory Event"}:
        raise MemoraError("Working memory and personal profiles cannot be published.")
    if not b.get("id"):
        raise MemoraError("Migrate the note before publication.")
    sources = [
        {"resource": s["resource"]}
        for s in data.get("sources", [])
        if urlsplit(s["resource"]).scheme in {"https", "http", "urn"}
    ]
    result = {
        "id": b["id"],
        "type": data["type"],
        "title": data.get("title", ""),
        "description": data.get("description", ""),
        "body": body.split("<!-- brain:relations -->")[0].strip(),
        "sources": sources,
    }
    if b.get("external_refs"):
        result["external_refs"] = [
            {
                field: ref[field]
                for field in (
                    "provider",
                    "instance",
                    "entity_type",
                    "entity_id",
                    "relation",
                    "observed_revision",
                )
                if field in ref
            }
            for ref in b["external_refs"]
        ]
    for field in ("entity_kind", "observation"):
        if b.get(field) is not None:
            result[field] = plain(b[field])
    # Only these source fields can enter the exact publication review.
    generated = data.get("generated", {})
    provenance = {
        key: value
        for key, value in {
            "created_at": b.get("created_at"),
            "created_by": b.get("created_by"),
            "updated_at": generated.get("at"),
            "updated_by": generated.get("by"),
            "valid_until": data.get("stale_after"),
        }.items()
        if value is not None
    }
    if b.get("shared_origin") or b.get("remote_origin"):
        # Importing a representation does not make the importer the source author.
        provenance = plain(b.get("provenance", {}))
    if provenance:
        result["provenance"] = provenance
    if result.get("observation"):
        observation = result["observation"]
        result["observation"] = {
            field: observation[field]
            for field in (
                "subject",
                "predicate",
                "value",
                "basis",
                "author",
                "observed_at",
                "valid_until",
            )
            if field in observation
        }
        result["observation"]["subject"] = {
            field: observation["subject"][field] for field in ("kind", "id")
        }
    return result


def propose(store, key, revision, destination, reason, actor, body=None):
    if not destination or not isinstance(destination, str):
        raise MemoraError("Select a destination space.")
    with store.lock():
        key, data, text = find(store, key)
        payload = projection(data, text)
        if body is not None:
            payload["body"] = body
        candidate = {
            "state": "candidate",
            "destination": destination,
            "reason": reason,
            "projection": payload,
            "fingerprint": fingerprint(data, text),
        }
        data["brain"]["publication"] = candidate
        return store.commit(key, data, text, actor, reason, revision)


def approve(store, key, revision, actor, reason):
    if not actor.startswith("human:") or not actor.removeprefix("human:").strip():
        raise MemoraError("Publication needs an explicit human review.")
    with store.lock():
        key, data, body = find(store, key)
        publication = data["brain"].get("publication", {})
        if publication.get("state") != "candidate":
            raise MemoraError("Propose and preview the content before approval.")
        if publication["fingerprint"] != fingerprint(data, body):
            raise Conflict("The content changed. Propose a new review.")
        publication.update(state="approved", approved_by=actor, approved_at=now())
        return store.commit(key, data, body, actor, reason, revision)


def export_shared(store, destination, output=None, *, standard=False):
    with store.lock():
        rows = list(notes(store))
        records, approved = [], {}
        for key, data, body in rows:
            p = data.get("brain", {}).get("publication", {})
            if p.get("destination") == destination and p.get("state") == "stale":
                raise Conflict("Approved content changed. A new review is required.")
            if p.get("destination") != destination or p.get("state") != "approved":
                continue
            if fingerprint(data, body) != p["fingerprint"]:
                raise Conflict("Approved content changed. A new review is required.")
            payload = copy.deepcopy(p["projection"])
            if not standard:
                payload.pop("provenance", None)
            if payload.get("observation"):
                validate(
                    {
                        "type": "Observation",
                        "sources": payload["sources"],
                        "brain": {"observation": payload["observation"]},
                    }
                )
            payload["origin"] = {
                "workspace": workspace(store)["id"],
                "revision": data["brain"]["revision"],
            }
            payload["review"] = {"by": p["approved_by"], "at": p["approved_at"]}
            records.append(payload)
            approved[data["brain"]["id"]] = data
        if not records:
            raise MemoraError("No approved content exists for this destination.")
        edges = []
        for origin, data in approved.items():
            for e in data["brain"].get("relations", []):
                if e.get("target_id") in approved:
                    edges.append(
                        {
                            "id": e["id"],
                            "origin": origin,
                            "target": e["target_id"],
                            "type": e["type"],
                        }
                    )
        targets = set(approved) | {e["id"] for e in edges}
        for record in records:
            if (
                record.get("observation")
                and record["observation"]["subject"]["id"] not in targets
            ):
                raise MemoraError(
                    "Approve the observation subject and its relation endpoints too."
                )
        result = {
            "format": "context-knowledge-v1",
            "destination": destination,
            "records": records,
            "relations": edges,
        }
        result["sha256"] = digest(json_text(result))
        if output:
            output = Path(output).expanduser().resolve()
            if output.exists() or output.is_relative_to(store.root):
                raise MemoraError("Use a new export file outside the workspace.")
            atomic(output, json_text(result))
        return result


def migrate(store, apply=False):
    with store.lock():
        rows = list(notes(store))
        pending = [
            (key, data, body)
            for key, data, body in rows
            if not data.get("brain", {}).get("id")
            or any(
                not e.get("id") or not e.get("target_id")
                for e in data.get("brain", {}).get("relations", [])
            )
        ]
        result = {"apply": apply, "notes": len(pending), "backup": None}
        if not apply or not pending:
            return result
        backup = store.cache / "backups" / uuid.uuid4().hex
        shutil.copytree(store.bundle, backup / "knowledge")
        result["backup"] = str(backup)
        identities = {
            key: d.get("brain", {}).get("id") or str(uuid.uuid4()) for key, d, _ in rows
        }
        for key, data, body in pending:
            old_hash = content_hash(data, body)
            data.setdefault("brain", {})["id"] = identities[key]
            for e in data["brain"].get("relations", []):
                e.setdefault("id", str(uuid.uuid4()))
                if e["target"] in identities:
                    e["target_id"] = identities[e["target"]]
            for review in (
                data.get("verified", [])
                if isinstance(data.get("verified", []), list)
                else [data["verified"]]
            ):
                if review.get("brain", {}).get("content_hash") == old_hash:
                    review["brain"]["content_hash"] = content_hash(data, body)
            store.commit(
                key,
                data,
                body,
                "process:migration",
                "Assign stable graph identities.",
                data.get("brain", {}).get("revision", 1),
            )
        return result


def import_shared(store, path):
    """Validate a selective package, then apply its records as one recoverable write."""
    import tempfile
    from .store import Store

    store.require_ignored_memory()
    raw = Path(path).read_bytes()
    if len(raw) > 16 * 1024 * 1024:
        raise MemoraError("The shared package exceeds 16 MiB.")
    package = json.loads(raw)
    payload = dict(package)
    checksum = payload.pop("sha256", None)
    if (
        set(package) != {"format", "destination", "records", "relations", "sha256"}
        or package.get("format") != "context-knowledge-v1"
        or digest(json_text(payload)) != checksum
    ):
        raise MemoraError("The shared package format or checksum is not valid.")
    space = workspace(store)
    if package.get("destination") not in {space["id"], space["name"]}:
        raise MemoraError("The package has another destination space.")
    records, edges = package.get("records"), package.get("relations")
    if not isinstance(records, list) or not isinstance(edges, list) or not records:
        raise MemoraError("The shared package needs records and relations.")
    incoming = {}
    for record in records:
        if not isinstance(record, dict) or set(record) - {
            "id",
            "type",
            "title",
            "description",
            "body",
            "sources",
            "entity_kind",
            "observation",
            "origin",
            "review",
            "external_refs",
            "provenance",
        }:
            raise MemoraError("The shared record has unknown fields.")
        identity = record.get("id")
        try:
            uuid.UUID(identity)
        except (ValueError, TypeError, AttributeError) as exc:
            raise MemoraError("The shared entity identity is not valid.") from exc
        if (
            identity in incoming
            or record.get("type") not in store.types()
            or record["type"] in {"Checkpoint", "Task", "Profile", "Memory Event"}
        ):
            raise MemoraError("The shared entity type or identity is not valid.")
        if not all(
            isinstance(record.get(f), str) for f in ["title", "description", "body"]
        ):
            raise MemoraError("The shared record needs text fields.")
        if not isinstance(record.get("sources"), list) or any(
            set(s) != {"resource"}
            or urlsplit(s["resource"]).scheme not in {"https", "http", "urn"}
            for s in record["sources"]
        ):
            raise MemoraError("Shared sources must use public reference identifiers.")
        if (
            not isinstance(record.get("origin"), dict)
            or not isinstance(record["origin"].get("revision"), int)
            or record["origin"]["revision"] < 1
        ):
            raise MemoraError("The shared record needs an origin revision.")
        if not isinstance(record.get("review"), dict) or not str(
            record["review"].get("by", "")
        ).startswith("human:"):
            raise MemoraError("The shared record needs a publication review.")
        incoming[identity] = record
    edge_ids = set()
    for edge in edges:
        if not isinstance(edge, dict) or set(edge) != {
            "id",
            "origin",
            "target",
            "type",
        }:
            raise MemoraError("The shared relation fields are not valid.")
        try:
            uuid.UUID(edge["id"])
        except (ValueError, TypeError, AttributeError) as exc:
            raise MemoraError("The shared relation identity is not valid.") from exc
        if (
            edge["id"] in edge_ids
            or edge["origin"] not in incoming
            or edge["target"] not in incoming
            or edge["origin"] == edge["target"]
            or edge["type"] not in store.relation_types()
        ):
            raise MemoraError("The shared relation endpoints or type are not valid.")
        edge_ids.add(edge["id"])
    for record in records:
        if record.get("observation"):
            subject = record["observation"]["subject"]
            targets = incoming if subject["kind"] == "entity" else edge_ids
            if subject["id"] not in targets:
                raise MemoraError("The shared observation subject is missing.")
    with store.lock():
        existing = {
            d.get("brain", {}).get("id"): (key, d, body)
            for key, d, body in notes(store)
        }
        mapping = {
            identity: existing[identity][0]
            if identity in existing
            else "/nodes/" + identity + ".md"
            for identity in incoming
        }
        with tempfile.TemporaryDirectory(prefix="memora-share-") as temp:
            stage = Store(Path(temp))
            if (store.root / "docs").exists():
                shutil.copytree(store.root / "docs", stage.root / "docs")
            writes, changed = [], 0
            for identity, record in incoming.items():
                if identity in existing:
                    _, old, _ = existing[identity]
                    origin = old.get("brain", {}).get("shared_origin", {})
                    if origin.get("hash") == digest(json_text(record)) and origin.get(
                        "local_fingerprint"
                    ) == share_local_hash(old, existing[identity][2]):
                        continue
                    raise Conflict(
                        "Shared content diverged. Review the local and incoming records."
                    )
                data = {
                    "type": record["type"],
                    "title": record["title"],
                    "description": record["description"],
                    "sources": record["sources"],
                    "tags": ["shared-knowledge"],
                    "brain": {
                        "id": identity,
                        "scope": "shared",
                        "state": "provisional",
                        "relations": [
                            {
                                "id": e["id"],
                                "type": e["type"],
                                "target": mapping[e["target"]],
                                "target_id": e["target"],
                            }
                            for e in edges
                            if e["origin"] == identity
                        ],
                    },
                }
                for field in [
                    "entity_kind",
                    "observation",
                    "external_refs",
                    "provenance",
                ]:
                    if field in record:
                        data["brain"][field] = record[field]
                apply_validity(data, record)
                data["brain"]["shared_origin"] = {
                    "hash": digest(json_text(record)),
                    **record["origin"],
                    "review": copy.deepcopy(record["review"]),
                }
                # Local changes are detected independently from the untrusted origin label.
                content = record["body"]
                result = stage.create(
                    data,
                    content,
                    "process:shared-import",
                    "Import reviewed knowledge.",
                    mapping[identity],
                )
                final, body = stage.read(result["path"])
                # Compare projected content instead of embedding a recursive fingerprint.
                final["brain"]["shared_origin"]["local_fingerprint"] = share_local_hash(
                    final, body
                )
                from .codec import dump, load

                after = dump(final, body)
                event_path = result["event"]
                event, event_body = load(stage.path(event_path).read_text())
                event["brain"]["after"] = after
                writes.extend(
                    [
                        {
                            "path": mapping[identity],
                            "content": after,
                            "before_hash": None,
                        },
                        {
                            "path": event_path,
                            "content": dump(event, event_body),
                            "before_hash": None,
                        },
                    ]
                )
                changed += 1
            if writes:
                for entry in writes:
                    if store.path(entry["path"]).exists():
                        raise Conflict("The import path has local content.")
                from .bundles import identity as bundle_identity

                atomic(
                    store.cache / "import-transaction.json",
                    json_text({"writes": writes, "identity": bundle_identity(store)}),
                )
                from .bundles import recover_import

                recover_import(store)
            return {"imported": changed, "unchanged": len(records) - changed}


def share_local_hash(data, body):
    value = plain(data)
    value.get("brain", {}).get("shared_origin", {}).pop("local_fingerprint", None)
    return fingerprint(value, body)
