"""Read OKF notes. Keep unknown fields."""

from __future__ import annotations

import hashlib
import io
import json
import posixpath
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt
from ruamel.yaml import YAML

STATES = {
    "provisional": "draft",
    "settled": "stable",
    "disputed": "draft",
    "discarded": "deprecated",
    "superseded": "deprecated",
}
WORK_STATES = {"open", "in_progress", "done", "cancelled"}
SCOPE_STATES = {"shared", "pending"}
TYPES = [
    "Entity",
    "Observation",
    "Profile",
    "Idea",
    "Concept",
    "Fact",
    "Decision",
    "Task",
    "Procedure",
    "Document",
    "System",
    "Project",
    "Repository",
    "Source",
    "Checkpoint",
]
RELATIONS = [
    "belongs_to",
    "depends_on",
    "supports",
    "contradicts",
    "replaces",
    "explains",
    "documents",
    "implements",
    "validates",
    "derived_from",
    "related_to",
    "observes",
]
BEGIN = "<!-- brain:relations -->"
END = "<!-- /brain:relations -->"


class MemoraError(Exception):
    """An action cannot complete."""


class Conflict(MemoraError):
    """The note revision does not match."""


def now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def instant(value: str) -> datetime:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError) as exc:
        raise MemoraError("Use an ISO 8601 date with a UTC offset.") from exc
    if dt.tzinfo is None:
        raise MemoraError("The date needs a UTC offset.")
    return dt.astimezone(timezone.utc)


def plain(value):
    if isinstance(value, Mapping):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def json_text(value) -> str:
    return json.dumps(plain(value), ensure_ascii=False, sort_keys=True)


def load(text: str) -> tuple[dict, str]:
    match = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)(.*)\Z", text, re.DOTALL)
    if not match:
        raise MemoraError("The note needs YAML frontmatter.")
    try:
        data = YAML(typ="rt").load(match.group(1))
    except Exception as exc:
        raise MemoraError(f"The YAML is not valid: {exc}") from exc
    if (
        not isinstance(data, Mapping)
        or not isinstance(data.get("type"), str)
        or not data["type"].strip()
    ):
        raise MemoraError("The note needs a non-empty type.")
    if data["type"] == "Memory Event":
        return data, match.group(2)
    validate_fields(data)
    return data, match.group(2)


def dump(data: dict, body: str) -> str:
    yaml = YAML(typ="rt")
    yaml.width = 100
    out = io.StringIO()
    yaml.dump(data, out)
    return "---\n" + out.getvalue() + "---\n" + body.strip() + "\n"


def validate_fields(data: dict) -> None:
    brain = data.get("brain", {})
    if not isinstance(brain, Mapping):
        raise MemoraError("brain must be a mapping.")
    state = brain.get("state")
    if state is not None and state not in STATES:
        raise MemoraError("The knowledge state is not valid.")
    if state and data.get("status", STATES[state]) != STATES[state]:
        raise MemoraError("The OKF status does not match the knowledge state.")
    if data.get("status", "stable") not in {"draft", "stable", "deprecated"}:
        raise MemoraError("The OKF status is not valid.")
    if brain.get("work_state") is not None and brain["work_state"] not in WORK_STATES:
        raise MemoraError("The work state is not valid.")
    if brain.get("scope") is not None and brain["scope"] not in SCOPE_STATES:
        raise MemoraError("The memory scope must be shared or pending.")
    if "revision" in brain and (
        type(brain["revision"]) is not int or brain["revision"] < 1
    ):
        raise MemoraError("The revision must be a positive integer.")
    for field in ("projects", "repositories"):
        values = brain.get(field, [])
        if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
            raise MemoraError(f"{field} must contain paths.")
        if len(values) != len(set(values)):
            raise MemoraError(f"{field} must not contain duplicate paths.")
        for value in values:
            if not value.startswith("/"):
                raise MemoraError(f"{field} paths must start with '/'.")
            safe_path(value)
    if not isinstance(data.get("tags", []), list) or any(
        not isinstance(v, str) for v in data.get("tags", [])
    ):
        raise MemoraError("tags must contain text values.")
    for field in ("title", "description"):
        if field in data and not isinstance(data[field], str):
            raise MemoraError(f"{field} must contain text.")
    for key in ("stale_after",):
        if data.get(key):
            instant(data[key])
    for key in ("generated",):
        obj = data.get(key)
        if obj is not None:
            if not isinstance(obj, Mapping) or not isinstance(obj.get("by"), str):
                raise MemoraError("generated needs an actor.")
            if obj.get("at"):
                instant(obj["at"])
    sources = data.get("sources", [])
    if not isinstance(sources, list) or any(
        not isinstance(s, Mapping)
        or not isinstance(s.get("resource"), str)
        or not s["resource"].strip()
        for s in sources
    ):
        raise MemoraError("Each source needs a resource.")
    verified = data.get("verified", [])
    if isinstance(verified, Mapping):
        verified = [verified]
    if not isinstance(verified, list):
        raise MemoraError("verified must contain review records.")
    for v in verified:
        if not isinstance(v, Mapping) or not isinstance(v.get("by"), str):
            raise MemoraError("A review needs an actor.")
        if v.get("at"):
            instant(v["at"])
    external_refs = brain.get("external_refs", [])
    if not isinstance(external_refs, list):
        raise MemoraError("External references must be a list.")
    for ref in external_refs:
        if not isinstance(ref, Mapping) or any(
            not isinstance(ref.get(field), str) or not ref[field].strip()
            for field in (
                "provider",
                "instance",
                "entity_type",
                "entity_id",
                "relation",
            )
        ):
            raise MemoraError(
                "An external reference needs provider, instance, entity type, entity ID, and relation."
            )
        if not re.fullmatch(r"[a-z][a-z0-9_]*", ref["relation"]):
            raise MemoraError("The external relation type is not valid.")
        if "observed_revision" in ref and not isinstance(ref["observed_revision"], str):
            raise MemoraError("The observed revision must be text.")
    from .knowledge import validate as validate_knowledge

    validate_knowledge(data)
    relations = brain.get("relations", [])
    if not isinstance(relations, list):
        raise MemoraError("relations must be a list.")
    for relation in relations:
        if (
            not isinstance(relation, Mapping)
            or not isinstance(relation.get("type"), str)
            or not re.fullmatch(r"[a-z][a-z0-9_]*", relation["type"])
        ):
            raise MemoraError("A relation needs a type.")
        if not isinstance(relation.get("target"), str) or not relation[
            "target"
        ].startswith("/"):
            raise MemoraError("A typed relation needs a bundle path.")
        safe_path(relation["target"])


def safe_path(value: str) -> str:
    raw = unquote(value).lstrip("/")
    if not raw or "\\" in raw or "\x00" in raw or ".." in raw.split("/"):
        raise MemoraError("The path must stay inside the knowledge bundle.")
    p = Path(raw)
    if p.suffix != ".md" or p.name in {"index.md", "log.md"}:
        raise MemoraError("Use a concept path with an .md suffix.")
    return "/" + p.as_posix()


def render_relations(body: str, relations: list) -> str:
    pattern = re.escape(BEGIN) + r".*?" + re.escape(END)
    if body.count(BEGIN) != body.count(END) or body.count(BEGIN) > 1:
        raise MemoraError("The managed relation section is not valid.")
    clean = re.sub(pattern, "", body, flags=re.DOTALL).rstrip()
    if not relations:
        return clean
    lines = [BEGIN, "## Relations"]
    for r in relations:
        target = safe_path(r["target"])
        label = Path(target).stem.replace("[", "").replace("]", "")
        lines.append(f"- {r['type']}: [{label}](<{target}>)")
    return clean + "\n\n" + "\n".join(lines + [END])


def link_target(value: str, origin: str) -> str | None:
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or not parsed.path or parsed.path.endswith("/"):
        return None
    path = unquote(parsed.path)
    if not path.lower().endswith(".md"):
        return None
    normalized = posixpath.normpath(
        path
        if path.startswith("/")
        else posixpath.join(posixpath.dirname(origin), path)
    )
    return safe_path(normalized)


def body_links(body: str, origin: str) -> list[str]:
    result = []
    for token in MarkdownIt().parse(body):
        for child in token.children or []:
            if child.type == "link_open":
                target = link_target(child.attrGet("href") or "", origin)
                if target and target not in result:
                    result.append(target)
    return result


def relations(data: dict, body: str, origin: str) -> list[dict]:
    typed = plain(data.get("brain", {}).get("relations", []))
    rendered = render_relations(body, typed)
    old = re.search(re.escape(BEGIN) + r"(.*?)" + re.escape(END), body, re.DOTALL)
    new = re.search(re.escape(BEGIN) + r"(.*?)" + re.escape(END), rendered, re.DOTALL)
    if (old.group(1).strip() if old else None) != (
        new.group(1).strip() if new else None
    ):
        raise MemoraError("The Markdown relations do not match brain.relations.")
    targets = {r["target"] for r in typed}
    result = list(typed)
    result.extend(
        {"type": "related_to", "target": t}
        for t in body_links(body, origin)
        if t not in targets
    )
    return result


def graph_relations(data: dict, body: str, origin: str) -> list[dict]:
    """Return typed links and implicit links from project and repository scope."""
    result = relations(data, body, origin)
    seen = {(item["type"], item["target"]) for item in result}
    brain = data.get("brain", {})
    observation = brain.get("observation")
    if observation:
        subject = observation["subject"]
        if subject["kind"] == "entity":
            result.append(
                {
                    "type": "observes",
                    "target": "/unresolved/" + subject["id"] + ".md",
                    "target_id": subject["id"],
                }
            )
        else:
            result.append(
                {
                    "type": "observes",
                    "target": "relation:" + subject["id"],
                    "subject_relation_id": subject["id"],
                }
            )
    for field in ("projects", "repositories"):
        for target in brain.get(field, []):
            edge = ("belongs_to", target)
            if edge not in seen:
                result.append({"type": edge[0], "target": edge[1]})
                seen.add(edge)
    return result


def content_hash(data: dict, body: str) -> str:
    obj = plain(data)
    for key in ("verified", "generated", "status"):
        obj.pop(key, None)
    b = obj.get("brain", {})
    for key in (
        "revision",
        "state",
        "work_state",
        "last_event",
        "created_at",
        "language",
        "publication",
    ):
        b.pop(key, None)
    return hashlib.sha256((json_text(obj) + "\n" + body).encode()).hexdigest()


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def score(
    data: dict, body: str, at: str | None = None, contradicted: bool = False
) -> dict:
    value = 50 if data.get("sources") else 25
    reasons = [
        "A source is recorded." if value == 50 else "No concrete source is recorded."
    ]
    verified = data.get("verified", [])
    if isinstance(verified, Mapping):
        verified = [verified]
    current = content_hash(data, body)
    valid = [
        v
        for v in verified
        if v.get("brain", {}).get("content_hash") == current
        and v.get("at")
        and v.get("brain", {}).get("reason")
    ]
    human = [v for v in valid if v["by"].startswith("human:")]
    machine = [
        v
        for v in valid
        if not v["by"].startswith("human:")
        and v.get("brain", {}).get("evidence")
        and data.get("sources")
    ]
    if machine:
        value = 75
        reasons.append("A current source check is recorded.")
    if human:
        value = 90
        reasons.append("A current user confirmation is recorded.")
    if human and any(v.get("brain", {}).get("independent") for v in machine):
        value = 100
        reasons.append("An independent check is recorded.")
    current_time = instant(at or now())
    stale = bool(
        data.get("stale_after") and current_time >= instant(data["stale_after"])
    )
    if stale:
        value = min(value, 50)
        reasons.append("The note has expired.")
    if contradicted or data.get("brain", {}).get("state") == "disputed":
        value = min(value, 25)
        reasons.append("A contradiction is open.")
    if data.get("brain", {}).get("observation", {}).get("basis") == "inferred":
        value = min(value, 25)
        reasons.append("This observation is an inference, not a direct finding.")
    return {"score": value, "reasons": reasons, "stale": stale}
