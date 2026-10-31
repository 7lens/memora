"""One application service for CLI and MCP memory operations."""

from __future__ import annotations

import copy
import unicodedata
from pathlib import Path

from .codec import MemoraError, Conflict, plain
from .compatibility import assert_context_ready
from .context import build_packet, current_repository
from .index import Index
from . import sessions


class MemoryService:
    def __init__(self, store):
        self.store = store

    def ingest(self, session_id, findings, preview=False):
        from .ingestion import ingest

        return ingest(self.store, session_id, findings, preview)

    def context(
        self,
        task,
        cwd=None,
        session_id=None,
        repository=None,
        project=None,
        max_bytes=12000,
        entity=None,
    ):
        if not isinstance(task, str) or not task.strip():
            raise MemoraError("Supply a task or search terms.")
        assert_context_ready(self.store)
        if cwd is not None and not Path(cwd).is_absolute():
            raise MemoraError("Use an absolute task directory.")
        if session_id:
            existing = sessions.read(self.store, session_id)
            if cwd != existing["cwd"] and (
                cwd is None
                or existing["cwd"] is None
                or Path(cwd).resolve() != Path(existing["cwd"]).resolve()
            ):
                raise MemoraError(
                    "A session cannot change repository paths. Start another task."
                )
            entity = existing.get("entity")
            repository = existing["repository"]
            project = project or existing.get("primary_project")
            if not project and len(existing["projects"]) == 1:
                project = existing["projects"][0]
            if project and project not in existing["projects"]:
                raise MemoraError("A session cannot change project scope.")
        index = Index(self.store)
        try:
            index.refresh()
            if cwd is not None and not Path(cwd).is_dir():
                raise MemoraError("The task directory does not exist.")
            found, code = (
                current_repository(index, Path(cwd)) if cwd is not None else (None, {})
            )
            if cwd is not None and not repository and not found:
                from types import SimpleNamespace
                from .registration import register

                repository = register(
                    self.store,
                    SimpleNamespace(
                        kind="repository",
                        cwd=Path(cwd),
                        name=Path(code["root"]).name,
                        description="Local task repository.",
                        project=[project] if project else [],
                        actor="process:task-start",
                        path=None,
                        source=["https://" + code["remote"]] if code["remote"] else [],
                    ),
                )["path"]
                index.refresh()
            context = build_packet(
                index,
                task,
                Path(cwd) if cwd is not None else None,
                repository,
                project,
                session_id,
                max_bytes,
                entity=entity,
            )
        finally:
            index.close()
        if session_id and context["projects"] != existing["projects"]:
            raise MemoraError("The project scope changed. Start another task.")
        session_id = session_id or sessions.start(
            self.store, context, Path(cwd) if cwd is not None else None
        )
        return {
            **context,
            "receipt": sessions.context_receipt(self.store, session_id, context),
        }

    def get_note(self, path, session_id=None):
        session = sessions.read(self.store, session_id) if session_id else None
        with self.store.lock():
            from .knowledge import find

            path, data, body = find(self.store, path)
        if session:
            scope = data.get("brain", {})
            repos, projects = scope.get("repositories", []), scope.get("projects", [])
            if (
                (session["repository"] or session["projects"])
                and (repos or projects)
                and not (
                    path == session["repository"]
                    or path in session["projects"]
                    or session["repository"] in repos
                    or set(projects) & set(session["projects"])
                )
            ):
                raise MemoraError("The note belongs to another task scope.")
        if session_id:
            sessions.record(
                self.store,
                session_id,
                "note_returned",
                {"path": path, "revision": data["brain"]["revision"]},
            )
        return {"path": path, "metadata": plain(data), "body": body}

    def remember(
        self,
        session_id,
        kind,
        title,
        description,
        body,
        reason,
        sources=None,
        tags=None,
        path=None,
        revision=None,
        external_refs=None,
    ):
        session = sessions.read(self.store, session_id)
        if kind not in {
            "Idea",
            "Concept",
            "Fact",
            "Decision",
            "Procedure",
            "Document",
            "System",
            "Profile",
            "Source",
        }:
            raise MemoraError("Save knowledge here. Use checkpoint for task progress.")
        if not all(
            isinstance(s, str) and s.strip() for s in [title, description, body, reason]
        ):
            raise MemoraError("Supply a title, description, content, and reason.")
        if (
            kind == "Decision"
            and "reason" not in body.lower()
            and "because" not in body.lower()
        ):
            raise MemoraError("A Decision must explain its reason in the content.")
        if kind == "Fact" and not sources:
            raise MemoraError(
                "A Fact needs a source. Save an unsourced claim as an Idea."
            )
        scope = {
            "repositories": [session["repository"]] if session["repository"] else [],
            "projects": session["projects"],
        }

        def same_scope(repositories, projects):
            if scope["repositories"]:
                return set(repositories) == set(scope["repositories"])
            return not repositories and set(projects) == set(scope["projects"])

        index = Index(self.store)
        try:
            index.refresh()

            def normalize(value):
                return unicodedata.normalize("NFKC", value).casefold().strip()

            matches = [
                n
                for n in index.all()
                if n["type"] == kind
                and normalize(n["title"]) == normalize(title)
                and same_scope(n["repositories"], n["projects"])
                and n["state"] not in {"discarded", "superseded"}
            ]
        finally:
            index.close()
        if not path and matches:
            return {
                "state": "existing_note",
                "matches": [
                    {"path": n["path"], "revision": n["revision"]} for n in matches
                ],
                "message": "Read the existing note. Update it with its path and revision.",
            }
        actor = "agent:local-memory"
        if path:
            with self.store.lock():
                data, _ = self.store.read(path)
                if data["type"] != kind:
                    raise MemoraError("Keep the note type when you update it.")
                b = data.get("brain", {})
                if not same_scope(b.get("repositories", []), b.get("projects", [])):
                    raise MemoraError("The note belongs to another scope.")
                if revision is None:
                    raise Conflict("Supply the current note revision.")
                data = copy.deepcopy(data)
                data.update({"title": title, "description": description})
                data["tags"] = list(dict.fromkeys(data.get("tags", []) + (tags or [])))
                data["sources"] = list(data.get("sources", []))
                for source in sources or []:
                    if source not in data["sources"]:
                        data["sources"].append(source)
                if external_refs is not None:
                    data["brain"]["external_refs"] = external_refs
                result = self.store.commit(path, data, body, actor, reason, revision)
        else:
            data = {
                "type": kind,
                "title": title,
                "description": description,
                "tags": tags or [kind.lower()],
                "sources": sources or [],
                "brain": {
                    **scope,
                    "state": "provisional",
                    "external_refs": external_refs or [],
                },
            }
            if not any(scope.values()):
                data["brain"]["scope"] = "shared"
            result = self.store.create(data, body, actor, reason)
        sessions.record(self.store, session_id, "knowledge_saved", result)
        return {
            "state": "saved_local",
            **result,
            "privacy": "private; no remote publication",
        }
