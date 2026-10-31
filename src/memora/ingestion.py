"""Validate extracted findings and save one private, recoverable batch."""

from __future__ import annotations

import re
import hashlib
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import quote, urlsplit

from . import sessions
from .codec import MemoraError, digest, json_text, plain
from .service import MemoryService
from .standard import validate_schema
from .store import Store, atomic

SECRET_PATTERNS = [
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16})\b",
    r"(?i)\bauthorization\s*[:=]\s*bearer\s+\S+",
    r"(?i)\b(?:password|client_secret|access_token|refresh_token|api_key)\s*[:=]\s*[\"']?[^\s\"']{8,}",
]


def check_content(finding: dict) -> None:
    text = json_text(finding)
    if any(re.search(pattern, text) for pattern in SECRET_PATTERNS):
        raise MemoraError(
            "Remove credentials from the extracted finding before capture."
        )
    if (
        len(
            re.findall(
                r"(?im)^(?:user|assistant|system|developer)\s*:", finding["body"]
            )
        )
        >= 2
    ):
        raise MemoraError("Save conclusions with sources instead of a chat transcript.")
    for source in finding["sources"]:
        url = urlsplit(source["resource"])
        if (
            url.username
            or url.password
            or (url.scheme in {"http", "https"} and not url.hostname)
        ):
            raise MemoraError("Source references cannot contain URL credentials.")


def repository_evidence(cwd: Path, file: str) -> dict:
    from .context import repo_identity

    code = repo_identity(cwd)
    if not code.get("root") or not code.get("revision"):
        raise MemoraError("Select a Git repository with a commit.")
    root = Path(code["root"]).resolve()
    target = (root / file).resolve()
    if (
        not target.is_relative_to(root)
        or not target.is_file()
        or ".git" in target.relative_to(root).parts
    ):
        raise MemoraError("Select a source file inside the repository.")
    relative = target.relative_to(root).as_posix()
    # Read only tracked files. This avoids collecting local credential files by accident.
    tracked = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--error-unmatch", "--", relative],
        capture_output=True,
        check=False,
    )
    if tracked.returncode:
        raise MemoraError("Repository evidence must name a tracked file.")
    if target.stat().st_size > 8 * 1024 * 1024:
        raise MemoraError("The evidence file exceeds 8 MiB.")
    checksum = hashlib.sha256(target.read_bytes()).hexdigest()
    repository = code.get("remote") or digest(str(root))
    return {
        "resource": "urn:memora:git:"
        + quote(repository, safe="")
        + ":"
        + code["revision"]
        + ":"
        + quote(relative, safe="")
        + ":sha256:"
        + checksum,
        "revision": code["revision"],
        "path": relative,
        "sha256": checksum,
        "claim": "File identity only. No source content or source verification is recorded.",
    }


def ingest(store, session_id: str, document: dict, preview: bool = False) -> dict:
    validate_schema(document, "ingestion")
    for finding in document["findings"]:
        check_content(finding)
    session = sessions.read(store, session_id)
    store.require_ignored_memory()
    with store.lock():
        with tempfile.TemporaryDirectory(prefix="memora-ingest-") as directory:
            stage = Store(Path(directory))
            shutil.copytree(store.bundle, stage.bundle, dirs_exist_ok=True)
            if (store.root / "docs").exists():
                shutil.copytree(store.root / "docs", stage.root / "docs")
            atomic(sessions.session_path(stage, session_id), json_text(session))
            service = MemoryService(stage)
            results = []
            for finding in document["findings"]:
                result = service.remember(
                    session_id,
                    finding["type"],
                    finding["title"],
                    finding["description"],
                    finding["body"],
                    finding["reason"],
                    sources=finding["sources"],
                    tags=finding.get("tags"),
                    path=finding.get("path"),
                    revision=finding.get("revision"),
                    external_refs=finding.get("external_refs"),
                )
                if result["state"] == "existing_note":
                    equal = []
                    for match in result["matches"]:
                        metadata, body = stage.read(match["path"])
                        if (
                            body.split("<!-- brain:relations -->")[0].strip()
                            == finding["body"].strip()
                            and metadata.get("description") == finding["description"]
                            and plain(metadata.get("sources", [])) == finding["sources"]
                            and (
                                finding.get("external_refs") is None
                                or plain(metadata["brain"].get("external_refs", []))
                                == finding["external_refs"]
                            )
                        ):
                            equal.append(match)
                    result["state"] = "unchanged" if equal else "needs_review"
                results.append(result)
            writes = []
            for target in sorted(stage.bundle.rglob("*.md")):
                if target.name in {"index.md", "log.md"}:
                    continue
                key = "/" + target.relative_to(stage.bundle).as_posix()
                current = store.path(key)
                before = (
                    current.read_text(encoding="utf-8") if current.exists() else None
                )
                after = target.read_text(encoding="utf-8")
                if before != after:
                    writes.append(
                        {
                            "path": key,
                            "content": after,
                            "before_hash": digest(before)
                            if before is not None
                            else None,
                        }
                    )
            if not preview and writes:
                from .bundles import identity, recover_import

                atomic(
                    store.cache / "import-transaction.json",
                    json_text({"writes": writes, "identity": identity(store)}),
                )
                recover_import(store)
    if not preview:
        sessions.record(store, session_id, "findings_ingested", {"results": results})
    return {
        "preview": preview,
        "results": results,
        "saved": sum(r["state"] == "saved_local" for r in results),
        "privacy": "private drafts; no publication",
        "verification": "No evidence verification is implied.",
    }
