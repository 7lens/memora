"""Serve a local knowledge view with capture and publication review."""

from __future__ import annotations

import json
import sqlite3
import webbrowser
import secrets
from markdown_it import MarkdownIt
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs, urlencode

from .codec import MemoraError, Conflict, plain
from .index import Index
from .store import Store
from .viewer import data, render_data, version


def make_server(root: Path, port: int = 0, on_api_request=None) -> HTTPServer:
    memory_root = root.expanduser().resolve()

    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def selected_store(self):
            from .knowledge import select_workspace

            query = parse_qs(urlsplit(self.path).query)
            return select_workspace(
                Store(memory_root), query.get("workspace", ["personal"])[0]
            )

        def send_json(self, value, status=200):
            body = json.dumps(plain(value), ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            host = f"127.0.0.1:{self.server.server_port}"
            if (
                urlsplit(self.path).path != "/api/action"
                or self.headers.get("Host") != host
                or self.headers.get("Origin") != "http://" + host
                or self.headers.get("X-Brain-Token") != token
                or self.headers.get("Content-Type") != "application/json"
            ):
                self.send_error(403)
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 131072:
                    raise MemoraError("The request size is not valid.")
                request = json.loads(self.rfile.read(size))
                store = self.selected_store()
                from . import knowledge as k

                action = request.pop("action")
                if action == "entity":
                    result = store.create(
                        {
                            "type": "Entity",
                            "title": request["title"],
                            "description": request.get("description", request["title"]),
                            "tags": [request["kind"]],
                            "sources": request.get("sources", []),
                            "brain": {
                                "entity_kind": request["kind"],
                                "scope": "shared",
                            },
                        },
                        request.get("body", ""),
                        "human:local",
                        "Add a knowledge subject.",
                    )
                elif action == "capture":
                    note_type = request["type"]
                    if note_type not in {"Concept", "Fact", "Decision", "Procedure"}:
                        raise MemoraError("Select a supported knowledge type.")
                    result = store.create(
                        {
                            "type": note_type,
                            "title": request["title"],
                            "description": request["title"],
                            "sources": request.get("sources", []),
                            "tags": ["knowledge"],
                            "brain": {"scope": "shared"},
                        },
                        request.get("body", ""),
                        "human:local",
                        "Capture local knowledge.",
                    )
                elif action == "edit":
                    if (
                        type(request.get("revision")) is not int
                        or request["revision"] < 1
                    ):
                        raise MemoraError("Supply the current note revision.")
                    if (
                        not isinstance(request.get("title"), str)
                        or not request["title"].strip()
                    ):
                        raise MemoraError("Supply a note title.")
                    if not isinstance(request.get("body"), str):
                        raise MemoraError("Supply the note content as text.")
                    result = store.update(
                        request["key"],
                        {"title": request["title"]},
                        request["body"],
                        "human:local",
                        request["reason"],
                        request["revision"],
                    )
                elif action == "observe":
                    result = k.observe(
                        store,
                        actor="human:local",
                        reason="Record a local observation.",
                        **request,
                    )
                elif action == "propose":
                    result = k.propose(store, actor="human:local", **request)
                elif action == "approve":
                    result = k.approve(store, actor="human:local", **request)
                elif action == "relate":
                    result = k.relate(store, actor="human:local", **request)
                elif action == "export":
                    result = k.export_shared(store, request["destination"])
                else:
                    raise MemoraError("The local action does not exist.")
                self.send_json(result)
            except Conflict as exc:
                self.send_json({"error": str(exc)}, 409)
            except (MemoraError, ValueError, KeyError, TypeError, OSError) as exc:
                self.send_json({"error": str(exc)}, 400)

        def do_GET(self):
            path = urlsplit(self.path).path
            if path not in {"/", "/index.html", "/api/data", "/api/note"}:
                self.send_error(404)
                return
            host = self.headers.get("Host", "")
            if host != f"127.0.0.1:{self.server.server_port}":
                self.send_error(403)
                return
            origin = self.headers.get("Origin")
            if origin and urlsplit(origin).netloc != host:
                self.send_error(403)
                return
            if path == "/api/data" and on_api_request:
                on_api_request()
            try:
                selected = self.selected_store()
            except MemoraError as exc:
                self.send_json({"error": str(exc)}, 400)
                return
            if path == "/api/note":
                try:
                    from .knowledge import find

                    key = parse_qs(urlsplit(self.path).query).get("path", [""])[0]
                    note_path, metadata, text = find(selected, key)
                    self.send_json(
                        {
                            "path": note_path,
                            "metadata": metadata,
                            "body": text,
                            "html": MarkdownIt("commonmark", {"html": False}).render(
                                text.split("<!-- brain:relations -->")[0]
                            ),
                        }
                    )
                except (MemoraError, OSError) as exc:
                    self.send_json({"error": str(exc)}, 404)
                return
            index = Index(selected)
            try:
                index.refresh()
                tag = '"' + version(index) + '"'
                if path == "/api/data" and self.headers.get("If-None-Match") == tag:
                    self.send_response(304)
                    self.send_header("ETag", tag)
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    return
                graph = data(index, live=True)
                from .knowledge import workspace

                registry = Store(memory_root).cache / "workspaces.json"
                graph["capability"] = token
                graph["workspace"] = workspace(selected)
                graph["workspaces"] = ["personal"] + list(
                    json.loads(registry.read_text()) if registry.exists() else {}
                )
                if path == "/api/data":
                    body = json.dumps(graph, ensure_ascii=False).encode("utf-8")
                    content_type = "application/json; charset=utf-8"
                else:
                    body = render_data(graph).encode("utf-8")
                    content_type = "text/html; charset=utf-8"
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("ETag", tag)
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Cross-Origin-Resource-Policy", "same-origin")
                self.end_headers()
                self.wfile.write(body)
            except (MemoraError, OSError, ValueError, KeyError, sqlite3.Error) as exc:
                body = json.dumps({"error": str(exc)}).encode("utf-8")
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
            finally:
                index.close()

        def log_message(self, _format: str, *_args):
            return

    return HTTPServer(("127.0.0.1", port), Handler)


def view(root: Path, no_open: bool = False, workspace: str = "personal") -> dict:
    server = make_server(root)
    url = f"http://127.0.0.1:{server.server_port}/"
    if workspace != "personal":
        url += "?" + urlencode({"workspace": workspace})
    print(f"Live memory view: {url} (press Ctrl+C to stop)", flush=True)
    if not no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return {"url": url, "stopped": True}
