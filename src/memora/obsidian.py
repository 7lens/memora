"""A local editable vault with revision checks and retained conflict copies."""

from __future__ import annotations

import copy
import json
import os
import re
import uuid
from pathlib import Path

from ruamel.yaml import YAML

from . import knowledge as k
from .codec import (
    BEGIN,
    END,
    STATES,
    Conflict,
    MemoraError,
    digest,
    dump,
    graph_relations,
    now,
    plain,
    safe_path,
)
from .standard import LOCAL_TYPES
from .store import atomic

LINK_BEGIN = "<!-- memora:links -->"
LINK_END = "<!-- /memora:links -->"
FIELDS = {
    "memora_id",
    "memora_revision",
    "type",
    "title",
    "description",
    "tags",
    "state",
    "sources",
}
NEW_TYPES = {
    "Idea",
    "Concept",
    "Fact",
    "Decision",
    "Procedure",
    "Document",
    "System",
    "Source",
}
ACTOR = "process:obsidian"


def directory(store) -> Path:
    return store.root / "obsidian"


def cache(store) -> Path:
    return store.cache / "obsidian"


def state_path(store) -> Path:
    return cache(store) / "state.json"


def read_state(store) -> dict:
    path = state_path(store)
    if not path.exists():
        raise MemoraError("Run memora obsidian init first.")
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("format") != "memora-live-vault-v1":
        raise MemoraError("The live vault state has an unsupported format.")
    for entry in value["entries"].values():
        filename = Path(entry["file"])
        if (
            filename.is_absolute()
            or ".." in filename.parts
            or "\\" in str(filename)
            or not filename.parts
            or filename.parts[0] != "Notes"
            or filename.suffix != ".md"
        ):
            raise MemoraError("The managed note path must stay inside obsidian/Notes.")
    return value


def save_state(store, state) -> None:
    atomic(state_path(store), json.dumps(state, ensure_ascii=False, indent=2))


def require_local_vault(store) -> None:
    vault = directory(store)
    if vault.is_symlink() or not vault.resolve().is_relative_to(store.root):
        raise MemoraError("The live vault must stay inside this workspace.")
    if (store.root / ".git").exists():
        import subprocess

        result = subprocess.run(
            [
                "git",
                "-C",
                str(store.root),
                "check-ignore",
                "--no-index",
                "--",
                "obsidian/Notes/check.md",
                "obsidian/.obsidian/app.json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0 or len(result.stdout.splitlines()) != 2:
            raise MemoraError(
                "Add /obsidian/ to .gitignore before you create a private vault."
            )
        tracked = subprocess.run(
            ["git", "-C", str(store.root), "ls-files", "--", "obsidian"],
            capture_output=True,
            text=True,
            check=True,
        )
        if tracked.stdout.strip():
            raise MemoraError(
                "The private vault contains tracked files. Remove them from Git first."
            )
    for path in vault.rglob("*") if vault.exists() else []:
        if path.is_symlink():
            raise MemoraError("The live vault must not contain symbolic links.")


def initialize(store) -> dict:
    with store.lock():
        require_local_vault(store)
        vault = directory(store)
        if not state_path(store).exists():
            if vault.exists() and any(vault.iterdir()):
                raise Conflict(
                    "The obsidian directory already contains files. Keep them and use a new workspace."
                )
            (vault / "Notes").mkdir(parents=True, exist_ok=True)
            atomic(
                vault / ".obsidian" / "app.json",
                json.dumps(
                    {
                        "newFileLocation": "folder",
                        "newFileFolderPath": "Notes",
                        "attachmentFolderPath": "Attachments",
                        "alwaysUpdateLinks": True,
                    },
                    indent=2,
                ),
            )
            save_state(
                store, {"format": "memora-live-vault-v1", "entries": {}, "issues": []}
            )
    return synchronize(store)


def strip_section(body: str, begin: str, end: str) -> str:
    if body.count(begin) != body.count(end) or body.count(begin) > 1:
        raise MemoraError(
            "The managed links section is not complete. Restore both markers."
        )
    return re.sub(
        re.escape(begin) + r".*?" + re.escape(end), "", body, flags=re.DOTALL
    ).strip()


def read_editor(text: str, filename: str) -> tuple[dict, str]:
    if len(text.encode()) > 1024 * 1024:
        raise MemoraError("The note exceeds 1 MiB. Link to a source document.")
    if text.startswith("---\n") or text.startswith("---\r\n"):
        match = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)(.*)\Z", text, re.DOTALL)
        if not match:
            raise MemoraError("The YAML frontmatter is not complete.")
        try:
            metadata = plain(YAML(typ="safe").load(match.group(1))) or {}
        except Exception as exc:
            raise MemoraError(f"The YAML is not valid: {exc}") from exc
        if not isinstance(metadata, dict):
            raise MemoraError("Use a YAML mapping for note properties.")
        body = match.group(2)
    else:
        metadata, body = {}, text
    for field in metadata:
        if field not in FIELDS and not field.startswith("rel_"):
            raise MemoraError(
                f"The vault property {field} is not editable. Use Memora for other metadata."
            )
    defaults = {
        "type": "Idea",
        "title": Path(filename).stem,
        "description": "",
        "tags": [],
        "state": "provisional",
        "sources": [],
    }
    for key, value in defaults.items():
        metadata.setdefault(key, value)
    for field in ("type", "title", "description", "state"):
        if not isinstance(metadata[field], str):
            raise MemoraError(f"{field} must contain text.")
    if not metadata["title"].strip() or metadata["state"] not in STATES:
        raise MemoraError("Supply a title and a valid knowledge state.")
    if "memora_revision" in metadata and (
        type(metadata["memora_revision"]) is not int or metadata["memora_revision"] < 1
    ):
        raise MemoraError("Keep memora_revision as a positive integer.")
    for field, values in metadata.items():
        if field in {"tags", "sources"} or field.startswith("rel_"):
            if not isinstance(values, list) or any(
                not isinstance(v, str) for v in values
            ):
                raise MemoraError(f"{field} must be a list of text values.")
    return metadata, strip_section(body, LINK_BEGIN, LINK_END)


def note_name(data: dict) -> str:
    title = (
        re.sub(r"[^\w -]", "", data.get("title", "Note"), flags=re.UNICODE).strip()[:90]
        or "Note"
    )
    return "Notes/" + title + "--" + data["brain"]["id"][:8] + ".md"


def target_value(target: str, names: dict, rows: dict) -> str:
    identity = next((i for i, row in rows.items() if row[0] == target), None)
    return (
        "[[" + names[identity][:-3] + "]]" if identity in names else "memora:" + target
    )


def project(
    data: dict, body: str, names: dict, rows: dict, relation_types: dict
) -> str:
    b = data["brain"]
    metadata = {
        "memora_id": b["id"],
        "memora_revision": b["revision"],
        "type": data["type"],
        "title": data.get("title", ""),
        "description": data.get("description", ""),
        "tags": plain(data.get("tags", [])),
        "state": b.get("state", "provisional"),
        "sources": [s["resource"] for s in data.get("sources", [])],
    }
    for kind in relation_types:
        metadata["rel_" + kind] = [
            target_value(e["target"], names, rows)
            for e in b.get("relations", [])
            if e["type"] == kind
        ]
    # Keep undeclared historical relation types readable, but do not create new ones.
    for kind in {edge["type"] for edge in b.get("relations", [])} - set(relation_types):
        metadata["rel_" + kind] = [
            target_value(edge["target"], names, rows)
            for edge in b.get("relations", [])
            if edge["type"] == kind
        ]
    links = []
    key = rows[b["id"]][0]
    for edge in graph_relations(data, body, key):
        target = target_value(edge["target"], names, rows)
        if target.startswith("[["):
            links.append("- " + edge["type"] + ": " + target)
    clean = strip_section(body, BEGIN, END)
    if links:
        clean += (
            "\n\n"
            + LINK_BEGIN
            + "\n## Relations\n\n"
            + "\n".join(dict.fromkeys(links))
            + "\n"
            + LINK_END
        )
    return dump(metadata, clean)


def resolve_target(value: str, names: dict, rows: dict, aliases: dict) -> str:
    if value.startswith("memora:"):
        return safe_path(value.removeprefix("memora:"))
    match = re.fullmatch(r"\[\[([^\]|#]+)(?:\|[^\]]+)?\]\]", value)
    if not match:
        raise MemoraError("Use a quoted [[note link]] for each rel_ property.")
    name = match.group(1).removesuffix(".md")
    matches = {
        i
        for mapping in (names, aliases)
        for i, path in mapping.items()
        if name in {path[:-3], Path(path).stem}
    }
    if len(matches) != 1:
        raise MemoraError(f"The relation target is missing or ambiguous: {name}")
    return rows[matches.pop()][0]


def apply_editor(
    store, data: dict, body: str, metadata: dict, names: dict, rows: dict, aliases: dict
) -> dict:
    result = copy.deepcopy(data)
    if metadata["type"] != data["type"]:
        raise MemoraError("Keep the note type. Use Memora to change advanced metadata.")
    for field in ("title", "description", "tags"):
        result[field] = metadata[field]
    old_sources = {s["resource"]: s for s in result.get("sources", [])}
    result["sources"] = [
        old_sources.get(resource, {"resource": resource})
        for resource in dict.fromkeys(metadata["sources"])
    ]
    b = result.setdefault("brain", {})
    b["state"] = metadata["state"]
    old_edges = {(e["type"], e["target"]): e for e in b.get("relations", [])}
    edges = []
    allowed = set(store.relation_types()) | {kind for kind, _ in old_edges}
    for field, values in metadata.items():
        if not field.startswith("rel_"):
            continue
        kind = field.removeprefix("rel_")
        if kind not in allowed:
            raise MemoraError(f"The relation type is not declared: {kind}")
        for value in dict.fromkeys(values):
            target = resolve_target(value, names, rows, aliases)
            edges.append(
                copy.deepcopy(
                    old_edges.get((kind, target), {"type": kind, "target": target})
                )
            )
    b["relations"] = edges
    if result["type"] == "Fact" and not result["sources"]:
        raise MemoraError("A Fact needs a source. Use Idea for an unsourced claim.")
    if result["type"] == "Decision" and not any(
        word in body.lower() for word in ("reason", "because")
    ):
        raise MemoraError("A Decision must explain its reason in the content.")
    return result


def backup(store, text: str) -> None:
    path = cache(store) / "backups" / (digest(text) + ".md")
    if not path.exists():
        atomic(path, text)


def replace_editor(store, path: Path, text: str, expected: str | None) -> None:
    current = path.read_text(encoding="utf-8") if path.exists() else None
    if current != expected:
        if current is not None:
            backup(store, current)
        raise Conflict(
            "The Obsidian file changed during synchronization. Both versions remain available."
        )
    if current == text:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    staged = cache(store) / "staged" / (uuid.uuid4().hex + ".md")
    retired = cache(store) / "backups" / (uuid.uuid4().hex + ".md")
    atomic(staged, text)
    try:
        if current is not None:
            retired.parent.mkdir(parents=True, exist_ok=True)
            # Retain the actual displaced inode, including a save that races our
            # initial check. A normal atomic replace would discard that content.
            path.rename(retired)
            if retired.read_text(encoding="utf-8") != expected:
                try:
                    os.link(retired, path)
                except FileExistsError:
                    pass
                raise Conflict(
                    f"A concurrent save remains in {retired}. Review it before resolution."
                )
        try:
            # An exclusive link never replaces a new save made after the move.
            os.link(staged, path)
        except FileExistsError as exc:
            raise Conflict(
                f"A concurrent save remains in the vault. The displaced file is {retired}."
            ) from exc
        if retired.exists() and retired.read_text(encoding="utf-8") != expected:
            raise Conflict(
                f"A concurrent save remains in {retired}. Review it before resolution."
            )
    finally:
        staged.unlink(missing_ok=True)


def _same_content(left: tuple[dict, str], right: tuple[dict, str]) -> bool:
    def content(value):
        metadata, body = value
        return {
            k: v
            for k, v in metadata.items()
            if k not in {"memora_revision", "memora_id"}
            and not (k.startswith("rel_") and not v)
        }, body

    return content(left) == content(right)


def synchronize(store, resolution: tuple[str, str, int] | None = None) -> dict:
    from .compatibility import assert_context_ready

    assert_context_ready(store)
    with store.lock():
        require_local_vault(store)
        state = read_state(store)
        entries = state["entries"]
        rows = {
            d["brain"]["id"]: (key, d, body)
            for key, d, body in k.notes(store)
            if d["type"] not in LOCAL_TYPES
        }
        names = {i: entries[i]["file"] for i in rows if i in entries}
        used_names = {name.casefold() for name in names.values()}
        for identity, row in rows.items():
            if identity in names:
                continue
            filename = note_name(row[1])
            if filename.casefold() in used_names:
                filename = filename[:-3] + "--" + identity + ".md"
            names[identity] = filename
            used_names.add(filename.casefold())
        aliases = {i: entry["file"] for i, entry in entries.items()}
        file_ids = {entry["file"]: identity for identity, entry in entries.items()}
        files, issues, changed, imported = {}, [], 0, 0
        for path in sorted((directory(store) / "Notes").rglob("*.md")):
            relative = path.relative_to(directory(store)).as_posix()
            text = path.read_text(encoding="utf-8")
            try:
                metadata, body = read_editor(text, relative)
                identity = metadata.get("memora_id")
                if relative in file_ids and identity != file_ids[relative]:
                    raise Conflict(
                        "Keep memora_id unchanged. It identifies this existing note."
                    )
                if identity is None:
                    identity = str(
                        uuid.uuid5(uuid.NAMESPACE_URL, str(store.root) + "/" + relative)
                    )
                elif not isinstance(identity, str) or identity not in rows:
                    raise Conflict(
                        "The note identity is unknown. Keep memora_id unchanged."
                    )
                files.setdefault(identity, []).append((relative, text, metadata, body))
                if identity in rows:
                    names[identity] = relative
            except MemoraError as exc:
                issues.append(
                    {
                        "id": file_ids.get(relative),
                        "file": relative,
                        "message": str(exc),
                    }
                )
        issue_files = {i["file"] for i in issues}
        if resolution and resolution[0] not in rows:
            raise MemoraError("Use an existing Memora note ID to resolve a conflict.")
        for identity in sorted(set(rows) | set(files)):
            row, entry = rows.get(identity), entries.get(identity)
            candidates = files.get(identity, [])
            selected = resolution if resolution and resolution[0] == identity else None
            if selected and row[1]["brain"]["revision"] != selected[2]:
                raise Conflict(
                    "The memory revision changed. Read the current note before resolution."
                )
            if len(candidates) > 1:
                issues.extend(
                    {
                        "id": identity,
                        "file": c[0],
                        "message": "Duplicate memora_id. Keep one file for this identity.",
                    }
                    for c in candidates
                )
                continue
            filename = names.get(identity, candidates[0][0] if candidates else "")
            if filename in issue_files and not (selected and selected[1] == "memory"):
                continue
            raw = candidates[0][1] if candidates else None
            if filename in issue_files:
                raw = (directory(store) / filename).read_text(encoding="utf-8")
                issues = [issue for issue in issues if issue["file"] != filename]
            try:
                if row is None:
                    _, raw, metadata, body = candidates[0]
                    if metadata["type"] not in NEW_TYPES:
                        raise MemoraError(
                            "Create this advanced type through Memora first."
                        )
                    data = {
                        "type": metadata["type"],
                        "brain": {"id": identity, "scope": "pending"},
                    }
                    data = apply_editor(
                        store, data, body, metadata, names, rows, aliases
                    )
                    key = "/nodes/obsidian-" + identity + ".md"
                    store.commit(
                        key, data, body, ACTOR, "Create a private note from Obsidian."
                    )
                    row = rows[identity] = (key, *store.read(key))
                    names[identity] = filename = candidates[0][0]
                    imported += 1
                elif candidates:
                    _, raw, metadata, body = candidates[0]
                    if entry:
                        if not (selected and selected[1] == "memory") and (
                            metadata.get("memora_id") != identity
                            or metadata.get("memora_revision") != entry["revision"]
                        ):
                            raise Conflict(
                                "Keep memora_id and memora_revision unchanged."
                            )
                        dirty = not _same_content(
                            (metadata, body), read_editor(entry["text"], filename)
                        )
                    else:
                        dirty = True
                    latest = project(
                        row[1], row[2], names, rows, store.relation_types()
                    )
                    same = _same_content(
                        (metadata, body), read_editor(latest, filename)
                    )
                    if (
                        dirty
                        and not same
                        and not (selected and selected[1] == "memory")
                    ):
                        if (
                            entry
                            and row[1]["brain"]["revision"] != entry["revision"]
                            and not selected
                        ):
                            raise Conflict(
                                "Both Memora and Obsidian changed. Resolve this conflict explicitly."
                            )
                        data = apply_editor(
                            store, row[1], body, metadata, names, rows, aliases
                        )
                        store.commit(
                            row[0],
                            data,
                            body,
                            ACTOR,
                            "Save a private edit from Obsidian.",
                            row[1]["brain"]["revision"],
                        )
                        row = rows[identity] = (row[0], *store.read(row[0]))
                        imported += 1
                elif entry and not (selected and selected[1] == "memory"):
                    raise Conflict(
                        "The vault file is missing. Deletion does not delete memory. Restore it with --keep memory."
                    )
                text = project(row[1], row[2], names, rows, store.relation_types())
                replace_editor(store, directory(store) / filename, text, raw)
                changed += text != raw
                entries[identity] = {
                    "file": filename,
                    "key": row[0],
                    "revision": row[1]["brain"]["revision"],
                    "text": text,
                }
            except (MemoraError, OSError) as exc:
                if raw is not None:
                    backup(store, raw)
                issues.append(
                    {
                        "id": identity,
                        "file": filename,
                        "revision": row[1]["brain"]["revision"] if row else None,
                        "message": str(exc),
                    }
                )
        # A vanished source is retained as a conflict. Never silently resurrect or delete it.
        for identity in set(entries) - set(rows):
            issues.append(
                {
                    "id": identity,
                    "file": entries[identity]["file"],
                    "message": "The source note is missing. Review it in Memora.",
                }
            )
        state.update(issues=issues, last_sync=now())
        save_state(store, state)
        summary = {
            "path": str(directory(store)),
            "notes": len(entries),
            "imported": imported,
            "updated": changed,
            "issues": issues,
            "last_sync": state["last_sync"],
        }
        home = (
            "# Memora live vault\n\nThis private vault reads and edits local Memora knowledge.\nKeep the synchronization process running. New notes belong in Notes.\nUse rel_ properties for typed relations. Do not change identity or revision properties.\nEdits keep normal history and do not approve publication or verify evidence.\nProfiles, tasks, checkpoints, and events stay in Memora.\n\n"
            + f"Notes: {len(entries)}. Pending issues: {len(issues)}.\n"
        )
        if issues:
            home += (
                "\n## Pending issues\n\n"
                + "\n".join("- " + i["file"] + ": " + i["message"] for i in issues)
                + "\n"
            )
        home_path = directory(store) / "Memora.md"
        if not home_path.exists() or home_path.read_text(encoding="utf-8") != home:
            atomic(home_path, home)
        return summary
