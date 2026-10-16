"""Build a search index from Markdown notes."""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from .codec import (
    MemoraError,
    graph_relations,
    json_text,
    score,
)
from .store import Store, atomic


class Index:
    def __init__(self, store: Store):
        self.store = store
        self.db = sqlite3.connect(store.cache / "index.sqlite", timeout=15)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA busy_timeout = 15000")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS nodes(path TEXT PRIMARY KEY, stamp TEXT, data TEXT, body TEXT, edges TEXT);
            CREATE VIRTUAL TABLE IF NOT EXISTS search USING fts5(path UNINDEXED, title, description, body, tags);
            CREATE TABLE IF NOT EXISTS edges(origin TEXT, target TEXT, kind TEXT, UNIQUE(origin,target,kind));
            CREATE INDEX IF NOT EXISTS edge_target ON edges(target);
            CREATE INDEX IF NOT EXISTS edge_origin ON edges(origin);
        """)
        self.read_count = 0

    def close(self):
        self.db.close()

    def refresh(self, force: bool = False):
        with self.store.lock():
            known = {
                r["path"]: r["stamp"]
                for r in self.db.execute("SELECT path,stamp FROM nodes")
            }
            present = set()
            changed = False
            with self.db:
                for path in self.store.bundle.rglob("*.md"):
                    rel = "/" + path.relative_to(self.store.bundle).as_posix()
                    if rel.startswith("/events/") or path.name in {
                        "index.md",
                        "log.md",
                    }:
                        continue
                    if path.is_symlink():
                        raise MemoraError(
                            "A knowledge note must not be a symbolic link."
                        )
                    present.add(rel)
                    stat = path.stat()
                    stamp = f"{stat.st_mtime_ns}:{stat.st_size}:{stat.st_ino}"
                    if not force and known.get(rel) == stamp:
                        continue
                    data, body = self.store.read(rel)
                    self.read_count += 1
                    edges = graph_relations(data, body, rel)
                    self.db.execute(
                        "INSERT OR REPLACE INTO nodes VALUES(?,?,?,?,?)",
                        (rel, stamp, json_text(data), body, json_text(edges)),
                    )
                    self.db.execute("DELETE FROM search WHERE path=?", (rel,))
                    self.db.execute(
                        "INSERT INTO search VALUES(?,?,?,?,?)",
                        (
                            rel,
                            data.get("title", Path(rel).stem),
                            data.get("description", ""),
                            body,
                            " ".join(data.get("tags", [])),
                        ),
                    )
                    self.db.execute("DELETE FROM edges WHERE origin=?", (rel,))
                    self.db.executemany(
                        "INSERT OR IGNORE INTO edges VALUES(?,?,?)",
                        [(rel, e["target"], e["type"]) for e in edges],
                    )
                    changed = True
                for rel in known.keys() - present:
                    self.db.execute("DELETE FROM nodes WHERE path=?", (rel,))
                    self.db.execute("DELETE FROM search WHERE path=?", (rel,))
                    self.db.execute("DELETE FROM edges WHERE origin=?", (rel,))
                    changed = True
            # Stable IDs keep edges valid after a note file moves. Paths are local hints.
            identities, edge_ids = {}, set()
            graph_rows = list(self.db.execute("SELECT path,data,edges FROM nodes"))
            for row in graph_rows:
                identity = json.loads(row["data"]).get("brain", {}).get("id")
                if identity:
                    if identity in identities:
                        raise MemoraError("An entity identity occurs in two notes.")
                    identities[identity] = row["path"]
            with self.db:
                for row in graph_rows:
                    edges = json.loads(row["edges"])
                    dirty = False
                    for edge in edges:
                        if edge.get("id"):
                            if edge["id"] in edge_ids:
                                raise MemoraError(
                                    "A relation identity occurs more than once."
                                )
                            edge_ids.add(edge["id"])
                        target = identities.get(edge.get("target_id"))
                        if target and target != edge["target"]:
                            edge["target"] = target
                            dirty = True
                    if dirty:
                        self.db.execute(
                            "UPDATE nodes SET edges=? WHERE path=?",
                            (json_text(edges), row["path"]),
                        )
                        self.db.execute(
                            "DELETE FROM edges WHERE origin=?", (row["path"],)
                        )
                        self.db.executemany(
                            "INSERT OR IGNORE INTO edges VALUES(?,?,?)",
                            [(row["path"], e["target"], e["type"]) for e in edges],
                        )
            if changed or not (self.store.bundle / "index.md").exists():
                self.write_indexes()

    def write_indexes(self):
        groups = {}
        for row in self.db.execute("SELECT path,data FROM nodes ORDER BY path"):
            d = json.loads(row["data"])
            groups.setdefault(d["type"], []).append(
                (
                    row["path"],
                    d.get("title", Path(row["path"]).stem),
                    d.get("description", ""),
                )
            )
        # Small entry indexes let an agent inspect one type at a time.
        directory = self.store.bundle / "catalog"
        directory.mkdir(exist_ok=True)
        root = ["---", 'okf_version: "0.2"', "---", "# Knowledge", ""]
        wanted = set()
        for kind, items in sorted(groups.items()):
            slug = re.sub(r"[^a-z0-9]+", "-", kind.lower()).strip("-") or "other"
            # The hash prevents different type names from sharing an index.
            import hashlib

            folder = slug + "-" + hashlib.sha256(kind.encode()).hexdigest()[:8]
            wanted.add(folder)
            target = directory / folder / "index.md"
            text = (
                "# "
                + kind
                + "\n\n"
                + "\n".join(
                    f"- [{title.replace('[', '').replace(']', '').replace(chr(10), ' ')}](<{key}>) - {desc.replace(chr(10), ' ')}"
                    for key, title, desc in items
                )
                + "\n"
            )
            atomic(target, text)
            root.append(f"- [{kind}](catalog/{folder}/) - {len(items)} notes.")
        for old in directory.glob("*/index.md"):
            if old.parent.name not in wanted:
                old.unlink()
                old.parent.rmdir()
        atomic(self.store.bundle / "index.md", "\n".join(root) + "\n")

    def row(self, key: str) -> dict | None:
        row = self.db.execute("SELECT * FROM nodes WHERE path=?", (key,)).fetchone()
        return self.summary(row) if row else None

    def content(self, key: str) -> tuple[dict, str]:
        row = self.db.execute(
            "SELECT data, body FROM nodes WHERE path=?", (key,)
        ).fetchone()
        if row is None:
            raise MemoraError("The note is not in this context snapshot.")
        return json.loads(row["data"]), row["body"]

    def summary(self, row) -> dict:
        data = json.loads(row["data"])
        # Read-back validation also catches a damaged cache.
        from .codec import validate_fields

        validate_fields(data)
        b = data.get("brain", {})
        # A changed evidence snapshot invalidates its source check.
        reviews = data.get("verified", [])
        if isinstance(reviews, dict):
            reviews = [reviews]
        for review in reviews:
            evidence = review.get("brain", {}).get("evidence")
            if isinstance(evidence, dict):
                import hashlib

                artifact = self.store.bundle / evidence.get("resource", "").lstrip("/")
                valid = (
                    artifact.resolve().is_relative_to(self.store.bundle.resolve())
                    and artifact.is_file()
                )
                if not valid or hashlib.sha256(
                    artifact.read_bytes()
                ).hexdigest() != evidence.get("sha256"):
                    review.get("brain", {}).pop("content_hash", None)
        contradiction = self.db.execute(
            """SELECT 1 FROM edges e JOIN nodes n ON n.path = CASE WHEN e.origin=? THEN e.target ELSE e.origin END
            WHERE e.kind='contradicts' AND (e.origin=? OR e.target=?)
            AND COALESCE(json_extract(n.data,'$.brain.state'),'settled') NOT IN ('discarded','superseded') AND COALESCE(json_extract(n.data,'$.status'),'stable') != 'deprecated' LIMIT 1""",
            (row["path"], row["path"], row["path"]),
        ).fetchone()
        return {
            "id": b.get("id"),
            "entity_kind": b.get("entity_kind"),
            "observation": b.get("observation"),
            "publication": b.get("publication", {}),
            "path": row["path"],
            "type": data["type"],
            "title": data.get("title", Path(row["path"]).stem),
            "description": data.get("description", ""),
            "tags": data.get("tags", []),
            "projects": b.get("projects", []),
            "repositories": b.get("repositories", []),
            "state": b.get(
                "state",
                {
                    "stable": "settled",
                    "draft": "provisional",
                    "deprecated": "superseded",
                }[data.get("status", "stable")],
            ),
            "work_state": b.get("work_state"),
            "revision": b.get("revision", 1),
            "sources": data.get("sources", []),
            "generated": data.get("generated", {}),
            "verified": data.get("verified", []),
            "created_at": b.get("created_at"),
            "last_event": b.get("last_event"),
            "context": b.get("context", {}),
            "relations": json.loads(row["edges"]),
            "external_refs": b.get("external_refs", []),
            **score(data, row["body"], contradicted=bool(contradiction)),
        }

    def all(self):
        return [
            self.summary(r)
            for r in self.db.execute("SELECT * FROM nodes ORDER BY path")
        ]

    def search(
        self, query: str, limit: int = 50, scope: list[str] | None = None
    ) -> list[dict]:
        words = re.findall(r"[\w-]+", query, re.UNICODE)[:30]
        if not words:
            return []
        match = " OR ".join('"' + word.replace('"', '""') + '"' for word in words)
        clause, params = "", [match]
        if scope is not None:
            clause = """ AND (
                (json_array_length(COALESCE(json_extract(n.data,'$.brain.projects'),'[]'))=0
                 AND json_array_length(COALESCE(json_extract(n.data,'$.brain.repositories'),'[]'))=0)
                OR EXISTS(SELECT 1 FROM json_each(json_extract(n.data,'$.brain.projects'))
                          WHERE value IN (SELECT value FROM json_each(?)))
                OR EXISTS(SELECT 1 FROM json_each(json_extract(n.data,'$.brain.repositories'))
                          WHERE value IN (SELECT value FROM json_each(?))))"""
            params.extend([json.dumps(scope), json.dumps(scope)])
        params.append(limit)
        rows = self.db.execute(
            "SELECT n.* FROM search s JOIN nodes n ON n.path=s.path WHERE search MATCH ?"
            + clause
            + " ORDER BY bm25(search,0,4,3,1,2), n.path LIMIT ?",
            params,
        )
        return [self.summary(r) for r in rows]

    def scoped(self, field: str, key: str, limit: int = 100):
        if field not in {"projects", "repositories"}:
            raise MemoraError("The scope field is not valid.")
        rows = self.db.execute(
            f"SELECT * FROM nodes WHERE path=? OR EXISTS(SELECT 1 FROM json_each(json_extract(data,'$.brain.{field}')) WHERE value=?) ORDER BY path LIMIT ?",
            (key, key, limit),
        )
        return [self.summary(r) for r in rows]

    def neighbors(self, key: str, limit: int = 100):
        rows = self.db.execute(
            """SELECT DISTINCT n.* FROM nodes n JOIN edges e
            ON n.path=CASE WHEN e.origin=? THEN e.target ELSE e.origin END
            WHERE e.origin=? OR e.target=? ORDER BY n.path LIMIT ?""",
            (key, key, key, limit),
        )
        return [self.summary(r) for r in rows]

    def unknown_links(self):
        return [
            dict(r)
            for r in self.db.execute(
                "SELECT e.* FROM edges e LEFT JOIN nodes n ON n.path=e.target WHERE n.path IS NULL"
            )
        ]
