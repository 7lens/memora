"""Track memory compatibility across Memora releases."""

from __future__ import annotations

import json
import re
from pathlib import Path

from . import __version__
from .codec import MemoraError, now
from .store import Store, atomic

MARKER = ".memora-version.json"
LEGACY_MARKER = ".agent-brain-version.json"
VERSION_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def version_parts(value: str) -> tuple[int, int, int]:
    match = VERSION_RE.fullmatch(value)
    if not match:
        raise MemoraError(f"Invalid semantic version: {value}")
    return tuple(int(part) for part in match.groups())


def checkout_version(root: Path) -> str | None:
    manifest = root / "pyproject.toml"
    if not manifest.is_file():
        return None
    import tomllib

    try:
        value = tomllib.loads(manifest.read_text(encoding="utf-8"))["project"][
            "version"
        ]
    except (KeyError, OSError, tomllib.TOMLDecodeError) as exc:
        raise MemoraError(
            "The checkout version is not valid in pyproject.toml."
        ) from exc
    if not isinstance(value, str):
        raise MemoraError("The checkout version must be a string.")
    version_parts(value)
    return value


def has_memory(store: Store) -> bool:
    for path in store.bundle.rglob("*.md"):
        relative = path.relative_to(store.bundle)
        if path.name not in {"index.md", "log.md"} and relative.parts[0] != "events":
            return True
    return False


def marker_path(store: Store) -> Path:
    return store.bundle / MARKER


def marker_data(store: Store) -> dict | None:
    path = marker_path(store)
    if not path.exists():
        path = store.bundle / LEGACY_MARKER
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MemoraError(f"The local memory version file is invalid: {path}") from exc
    if (
        not isinstance(data, dict)
        or data.get("format") != 1
        or not isinstance(data.get("tool_version"), str)
        or not isinstance(data.get("history"), list)
    ):
        raise MemoraError(f"The local memory version file has an invalid shape: {path}")
    version_parts(data["tool_version"])
    return data


def status(store: Store) -> dict:
    current = __version__
    current_major = version_parts(current)[0]
    checkout = checkout_version(store.root)
    recorded = marker_data(store)
    memory_version = recorded["tool_version"] if recorded else None
    memory_major = version_parts(memory_version)[0] if memory_version else None

    if recorded is None:
        memory_status = "unmarked" if has_memory(store) else "empty"
    elif memory_major == current_major:
        memory_status = "compatible"
    else:
        memory_status = "reconsolidation_required"

    return {
        "tool_version": current,
        "checkout_version": checkout,
        "tool_update_required": checkout is not None and checkout != current,
        "memory_version": memory_version,
        "memory_status": memory_status,
        "reconsolidation_required": memory_status
        in {"unmarked", "reconsolidation_required"},
        "action": action(memory_status, memory_version, current, checkout),
    }


def action(
    memory_status: str,
    memory_version: str | None,
    tool_version: str,
    checkout: str | None,
) -> str:
    if checkout is not None and checkout != tool_version:
        return "Update the local CLI from this checkout before loading task context."
    if memory_status == "unmarked":
        return "Review CHANGELOG.md, validate the graph, then run memora reconcile."
    if memory_status == "reconsolidation_required":
        return (
            f"Read each major release procedure in CHANGELOG.md from {memory_version} "
            f"through {tool_version}, then run memora reconcile."
        )
    if memory_status == "empty":
        return "No memory migration is needed. The first note sets the baseline."
    return "No memory reconsolidation is needed for this major version."


def assert_context_ready(store: Store) -> None:
    result = status(store)
    if result["tool_update_required"]:
        raise MemoraError(
            f"The checkout uses Memora {result['checkout_version']}, but this CLI "
            f"is {result['tool_version']}. Update `.venv/bin/memora` from this checkout "
            "before loading task context."
        )
    if result["reconsolidation_required"]:
        raise MemoraError(
            f"Memory compatibility check: {result['memory_status']}. "
            f"Recorded memory version: {result['memory_version'] or 'unknown'}. "
            f"Current tool version: {result['tool_version']}. {result['action']} "
            "Do not load task context until this procedure is complete."
        )


def record_baseline(store: Store, actor: str, reason: str) -> None:
    if marker_path(store).exists():
        return
    previous = marker_data(store)
    if previous is not None:
        atomic(marker_path(store), json.dumps(previous, indent=2) + "\n")
        return
    data = {
        "format": 1,
        "tool_version": __version__,
        "history": [
            {
                "from": None,
                "to": __version__,
                "at": now(),
                "actor": actor,
                "reason": reason,
            }
        ],
    }
    atomic(marker_path(store), json.dumps(data, indent=2) + "\n")


def record_reconciliation(store: Store, actor: str, reason: str) -> dict:
    previous = marker_data(store)
    previous_version = previous["tool_version"] if previous else None
    history = previous["history"] if previous else []
    history.append(
        {
            "from": previous_version,
            "to": __version__,
            "at": now(),
            "actor": actor,
            "reason": reason,
        }
    )
    data = {"format": 1, "tool_version": __version__, "history": history}
    atomic(marker_path(store), json.dumps(data, indent=2) + "\n")
    return {
        "memory_version": previous_version,
        "tool_version": __version__,
        "history_entries": len(history),
    }
