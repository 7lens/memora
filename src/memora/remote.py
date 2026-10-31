"""Explicit authenticated knowledge transfer. Local capture needs no transport."""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import secrets
import shutil
import tempfile
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from . import knowledge as k
from .codec import MemoraError, Conflict, digest, now
from .store import Store, atomic


def canonical(value):
    try:
        import rfc8785
    except ImportError as exc:
        raise MemoraError("Install memora[remote] to use remote exchange.") from exc
    return rfc8785.dumps(value)


def seal(value):
    value = copy.deepcopy(value)
    value.pop("sha256", None)
    return {**value, "sha256": hashlib.sha256(canonical(value)).hexdigest()}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(url, body=None, token=None, form=False):
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = None
    if body is not None:
        headers["Content-Type"] = (
            "application/x-www-form-urlencoded" if form else "application/json"
        )
        data = (urlencode(body) if form else json.dumps(body)).encode()
    try:
        with build_opener(NoRedirect).open(
            Request(url, data=data, headers=headers), timeout=20
        ) as response:
            raw = response.read(16 * 1024 * 1024 + 1)
            if len(raw) > 16 * 1024 * 1024:
                raise MemoraError("The remote response exceeds 16 MiB.")
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        # No server body, credentials, or query URL enters a diagnostic.
        raise MemoraError(
            f"The remote request failed with HTTP {exc.code}."
            + (
                " Run remote pull to inspect revision conflicts."
                if exc.code == 409
                else ""
            )
        ) from None
    except (URLError, TimeoutError, ValueError):
        raise MemoraError(
            "The remote request failed. Local memory is available."
        ) from None


def secure_url(url):
    p = urlsplit(url)
    if (
        p.username
        or p.password
        or p.query
        or p.fragment
        or (
            p.scheme != "https"
            and not (
                p.scheme == "http" and p.hostname in {"localhost", "127.0.0.1", "::1"}
            )
        )
    ):
        raise MemoraError(
            "Use HTTPS, or HTTP on loopback, without credentials or query."
        )
    return url.rstrip("/")


def config_path(store):
    return store.cache / "remotes.json"


def read_config(store):
    path = config_path(store)
    return json.loads(path.read_text()) if path.exists() else {}


def save_config(store, value):
    atomic(config_path(store), json.dumps(value, indent=2))


def secret_file(path):
    path = Path(path).expanduser()
    if path.stat().st_mode & 0o077:
        raise MemoraError("Credential files must be private to their owner (mode 600).")
    return path.read_text().strip()


def token(store, name, remote):
    if remote.get("signed_out"):
        raise MemoraError("Sign in with remote login before transfer.")
    if remote.get("token_file"):
        return secret_file(remote["token_file"])
    path = store.cache / ("remote-" + name + "-credentials.json")
    credentials = json.loads(secret_file(path)) if path.exists() else {}
    if credentials.get("expires_at", 0) > time.time() + 60:
        return credentials["access_token"]
    if remote.get("secret_file"):
        result = request(
            remote["domain"] + "/oauth2/token",
            {
                "grant_type": "client_credentials",
                "client_id": remote["client_id"],
                "client_secret": secret_file(remote["secret_file"]),
                "scope": remote["scope"],
            },
            form=True,
        )
    elif credentials.get("refresh_token"):
        result = request(
            remote["domain"] + "/oauth2/token",
            {
                "grant_type": "refresh_token",
                "client_id": remote["client_id"],
                "refresh_token": credentials["refresh_token"],
            },
            form=True,
        )
    elif remote.get("local"):
        return None
    else:
        raise MemoraError("Sign in with remote login before transfer.")
    result["refresh_token"] = result.get(
        "refresh_token", credentials.get("refresh_token")
    )
    result["expires_at"] = time.time() + result["expires_in"]
    atomic(path, json.dumps(result))
    return result["access_token"]


def login(store, name, remote):
    verifier = secrets.token_urlsafe(48)
    state = secrets.token_urlsafe(32)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    result = {}
    redirect = remote.get("redirect_uri", "http://127.0.0.1:8766/callback")
    parsed = urlsplit(redirect)
    if parsed.hostname != "127.0.0.1" or parsed.scheme != "http" or not parsed.port:
        raise MemoraError(
            "Use a registered HTTP callback on 127.0.0.1 with an explicit port."
        )

    class Callback(BaseHTTPRequestHandler):
        def do_GET(self):
            incoming = urlsplit(self.path)
            args = parse_qs(incoming.query)
            if (
                incoming.path != parsed.path
                or args.get("state") != [state]
                or not args.get("code")
            ):
                self.send_response(400)
                self.end_headers()
                return
            result["code"] = args["code"][0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Sign-in complete. Close this window.")

        def log_message(self, *_args):
            pass

    with HTTPServer(("127.0.0.1", parsed.port), Callback) as server:
        server.timeout = 1
        url = (
            remote["domain"]
            + "/oauth2/authorize?"
            + urlencode(
                {
                    "response_type": "code",
                    "client_id": remote["client_id"],
                    "redirect_uri": redirect,
                    "scope": "openid " + remote["scope"],
                    "state": state,
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                    "resource": remote["url"],
                }
            )
        )
        webbrowser.open(url)
        deadline = time.monotonic() + 180
        while "code" not in result and time.monotonic() < deadline:
            server.handle_request()
    if "code" not in result:
        raise MemoraError("Sign-in timed out.")
    credentials = request(
        remote["domain"] + "/oauth2/token",
        {
            "grant_type": "authorization_code",
            "client_id": remote["client_id"],
            "code": result["code"],
            "redirect_uri": redirect,
            "code_verifier": verifier,
        },
        form=True,
    )
    credentials["expires_at"] = time.time() + credentials["expires_in"]
    atomic(
        store.cache / ("remote-" + name + "-credentials.json"), json.dumps(credentials)
    )
    return {"signed_in": True}


def export_v2(store, destination):
    from .bundles import identity

    pkg = k.export_shared(store, destination)
    pkg["format"] = "context-knowledge-v2"
    memory_identity = identity(store)
    pkg["origin"] = memory_identity["brain_id"]
    origins = {
        i: v.get("origin")
        for r in read_config(store).values()
        for i, v in r.get("baselines", {}).items()
    }
    for record in pkg["records"]:
        path, data, _ = k.find(store, record["id"])
        original = data["brain"].get("shared_origin") or data["brain"].get(
            "remote_origin", {}
        )
        record["origin"]["brain"] = (
            origins.get(record["id"])
            or original.get("brain")
            or memory_identity["notes"].get(path, "").partition(":")[0]
            or pkg["origin"]
        )
    return seal(pkg)


def recover(store):
    path = store.cache / "remote-transaction.json"
    if not path.exists():
        return
    journal = json.loads(path.read_text())
    for write in journal["writes"]:
        target = store.path(write["path"])
        current = target.read_text() if target.exists() else None
        if current == write["content"]:
            continue
        if (digest(current) if current is not None else None) != write["before"]:
            raise Conflict(
                "Remote recovery found a local edit. Keep both versions for review."
            )
        atomic(target, write["content"])
    if journal.get("initialize"):
        from .compatibility import record_baseline, marker_path

        if not marker_path(store).exists():
            record_baseline(
                store, "process:remote-pull", "Start memory from published knowledge."
            )
    save_config(store, journal["config"])
    path.unlink()


def apply_pull(store, name, remote, changes, cursor):
    """Stage all note and event writes. Keep local edits and incoming conflict data."""
    store.require_ignored_memory()
    from .standard import schema
    from jsonschema import Draft202012Validator, FormatChecker

    record_validator = Draft202012Validator(
        schema()["properties"]["records"]["items"], format_checker=FormatChecker()
    )
    if type(cursor) is not int or cursor < remote.get("cursor", 0):
        raise MemoraError("The remote change cursor cannot move backwards.")
    for change in changes:
        entry = change.get("entry", {}) if isinstance(change, dict) else {}
        try:
            uuid.UUID(entry["id"])
            uuid.UUID(entry["origin"])
            if (
                type(entry["revision"]) is not int
                or entry["revision"] < 1
                or entry["state"] not in {"published", "withdrawn"}
                or entry["id"] != entry["record"]["id"]
                or not record_validator.is_valid(entry["record"])
                or not isinstance(entry["relations"], list)
            ):
                raise ValueError
            for edge in entry["relations"]:
                uuid.UUID(edge["id"])
                uuid.UUID(edge["target"])
                if (
                    edge["origin"] != entry["id"]
                    or edge["target"] == entry["id"]
                    or edge["type"] not in store.relation_types()
                ):
                    raise ValueError
        except (KeyError, ValueError, TypeError, AttributeError) as exc:
            raise MemoraError("The published remote entry is not valid.") from exc
    with store.lock():
        recover(store)
        existing = {
            d["brain"]["id"]: (path, d, body) for path, d, body in k.notes(store)
        }
        from .compatibility import has_memory, marker_path

        initialize = not marker_path(store).exists() and not has_memory(store)
        baselines = remote.setdefault("baselines", {})
        latest = {}
        for change in changes:
            entry = change["entry"]
            previous = latest.get(entry["id"])
            if (
                previous
                and previous["revision"] == entry["revision"]
                and previous != entry
            ):
                raise MemoraError("One remote revision has conflicting content.")
            base = baselines.get(entry["id"], {})
            if base.get("origin") and base["origin"] != entry["origin"]:
                raise Conflict(
                    "The remote record origin changed. Keep both identities for review."
                )
            if entry["revision"] > max(
                baselines.get(entry["id"], {}).get("revision", 0),
                latest.get(entry["id"], {}).get("revision", 0),
            ):
                latest[entry["id"]] = entry
        for identity, entry in latest.items():
            if identity not in existing:
                continue
            _, data, body = existing[identity]
            base = baselines.get(identity)
            # Push establishes a baseline too. A repeated pull can recover after process failure.
            if not base or base.get("fingerprint") != k.fingerprint(data, body):
                atomic(
                    store.cache / ("remote-" + name + "-conflicts.json"),
                    json.dumps(
                        {
                            "time": now(),
                            "incoming": latest,
                            "reason": "Local content changed.",
                        }
                    ),
                )
                raise Conflict(
                    "Local and remote content differ. The incoming version is in the private conflict report."
                )
        with tempfile.TemporaryDirectory(prefix="memora-remote-stage-") as temp:
            stage = Store(Path(temp))
            shutil.copytree(store.bundle, stage.bundle, dirs_exist_ok=True)
            if (store.root / "docs").exists():
                shutil.copytree(store.root / "docs", stage.root / "docs")
            mapping = {identity: value[0] for identity, value in existing.items()}
            mapping.update(
                {
                    identity: mapping.get(identity, "/nodes/" + identity + ".md")
                    for identity in latest
                }
            )
            for identity, entry in latest.items():
                record = entry["record"]
                if record["type"] in {"Profile", "Task", "Checkpoint", "Memory Event"}:
                    raise MemoraError("Remote working memory is not permitted.")
                if identity in existing:
                    path, data, _ = existing[identity]
                    data = copy.deepcopy(data)
                    revision = data["brain"]["revision"]
                    data["brain"].pop("publication", None)
                else:
                    path, revision = mapping[identity], None
                    data = {
                        "type": record["type"],
                        "brain": {
                            "id": identity,
                            "scope": "shared",
                            "state": "provisional",
                        },
                        "tags": ["shared-knowledge"],
                    }
                for field in ["type", "title", "description", "sources"]:
                    data[field] = record[field]
                for field in [
                    "entity_kind",
                    "observation",
                    "external_refs",
                    "provenance",
                ]:
                    if field in record:
                        data["brain"][field] = record[field]
                    else:
                        data["brain"].pop(field, None)
                k.apply_validity(data, record)
                data["brain"]["remote_origin"] = {
                    "brain": entry["origin"],
                    "revision": record["origin"]["revision"],
                    "review": record["review"],
                }
                data["brain"]["relations"] = [
                    {
                        "id": e["id"],
                        "type": e["type"],
                        "target_id": e["target"],
                        "target": mapping.get(
                            e["target"], "/nodes/" + e["target"] + ".md"
                        ),
                    }
                    for e in entry["relations"]
                ]
                if entry["state"] == "withdrawn":
                    data["brain"]["state"] = "discarded"
                elif data["brain"].get("state") == "discarded":
                    data["brain"]["state"] = "provisional"
                if revision is None:
                    stage.create(
                        data,
                        record["body"],
                        "process:remote-pull",
                        "Read published knowledge.",
                        path,
                    )
                else:
                    stage.commit(
                        path,
                        data,
                        record["body"],
                        "process:remote-pull",
                        "Read published knowledge.",
                        revision,
                    )
                final, body = stage.read(path)
                baselines[identity] = {
                    "revision": entry["revision"],
                    "origin": entry["origin"],
                    "fingerprint": k.fingerprint(final, body),
                }
            writes = []
            for target in stage.bundle.rglob("*.md"):
                if target.name in {"log.md", "index.md"}:
                    continue
                rel = "/" + target.relative_to(stage.bundle).as_posix()
                original = store.path(rel)
                old = original.read_text() if original.exists() else None
                new = target.read_text()
                if new != old:
                    writes.append(
                        {
                            "path": rel,
                            "content": new,
                            "before": digest(old) if old is not None else None,
                        }
                    )
            remote["cursor"] = cursor
            config = read_config(store)
            config[name] = remote
            atomic(
                store.cache / "remote-transaction.json",
                json.dumps(
                    {"writes": writes, "config": config, "initialize": initialize}
                ),
            )
            recover(store)
    return {"received": len(latest), "cursor": cursor}


def add_commands(sub):
    parser = sub.add_parser(
        "remote", help="Connect and transfer reviewed knowledge on demand."
    )
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("schema")
    add = actions.add_parser("add")
    add.add_argument("name")
    add.add_argument("--url", required=True)
    add.add_argument("--space", required=True)
    add.add_argument("--domain")
    add.add_argument("--client-id")
    add.add_argument("--scope")
    add.add_argument("--redirect-uri", default="http://127.0.0.1:8766/callback")
    add.add_argument("--token-file")
    add.add_argument("--secret-file")
    add.add_argument("--local", action="store_true")
    add.add_argument(
        "--protocol",
        choices=["context-knowledge-v2", "memora-knowledge-v1"],
        default="memora-knowledge-v1",
    )
    for action in [
        "login",
        "logout",
        "status",
        "push",
        "pull",
        "resolve",
        "references",
    ]:
        p = actions.add_parser(action)
        p.add_argument("name")
        if action == "resolve":
            p.add_argument("--id", required=True)
            p.add_argument("--take", choices=["local", "remote"], required=True)
        if action == "references":
            p.add_argument("--id", required=True)
        if action == "push":
            p.add_argument(
                "--publish",
                action="store_true",
                help="Explicitly approve publication as an authorized human reviewer.",
            )
            p.add_argument("--preview", action="store_true")
    p = actions.add_parser("convert")
    p.add_argument("file", type=Path)
    p.add_argument("--output", required=True, type=Path)


def dispatch(store, args):
    if args.action == "schema":
        return json.loads(
            Path(__file__).with_name("knowledge.remote.schema.json").read_text()
        )
    if args.action == "convert":
        pkg = json.loads(args.file.read_text())
        payload = dict(pkg)
        checksum = payload.pop("sha256", None)
        from .codec import json_text

        if (
            pkg.get("format") != "context-knowledge-v1"
            or digest(json_text(payload)) != checksum
        ):
            raise MemoraError("The v1 package checksum is not valid.")
        from .bundles import identity

        payload.update(
            format="context-knowledge-v2", origin=identity(store)["brain_id"]
        )
        if args.output.exists() or args.output.resolve().is_relative_to(store.root):
            raise MemoraError("Use a new export file outside the workspace.")
        atomic(args.output, json.dumps(seal(payload)))
        return {"converted": True}
    if not __import__("re").fullmatch(r"[a-z][a-z0-9_-]{0,63}", args.name):
        raise MemoraError("Use a simple remote name.")
    with store.lock():
        recover(store)
    config = read_config(store)
    if args.action == "add":
        if args.name in config:
            raise Conflict("The remote exists. Keep its transfer state.")
        url = secure_url(args.url)
        uuid.UUID(args.space)
        if args.local and urlsplit(url).hostname not in {
            "localhost",
            "127.0.0.1",
            "::1",
        }:
            raise MemoraError("Local mode requires a loopback API.")
        if (
            not args.local
            and not args.token_file
            and not all([args.domain, args.client_id, args.scope])
        ):
            raise MemoraError(
                "Supply OAuth domain, client ID and scope, or a token file."
            )
        remote = {
            "url": url,
            "space": args.space,
            "local": args.local,
            "cursor": 0,
            "baselines": {},
            "protocol": args.protocol,
        }
        for field in [
            "domain",
            "client_id",
            "scope",
            "redirect_uri",
            "token_file",
            "secret_file",
        ]:
            if getattr(args, field, None):
                remote[field] = (
                    secure_url(getattr(args, field))
                    if field == "domain"
                    else getattr(args, field)
                )
        config[args.name] = remote
        save_config(store, config)
        return {"added": args.name}
    if args.name not in config:
        raise MemoraError("The remote is not configured.")
    remote = config[args.name]
    if args.action == "login":
        remote["signed_out"] = False
        if remote.get("token_file") or remote.get("secret_file") or remote.get("local"):
            token(store, args.name, remote)
            result = {"signed_in": True}
        else:
            result = login(store, args.name, remote)
        save_config(store, config)
        return result
    if args.action == "logout":
        path = store.cache / ("remote-" + args.name + "-credentials.json")
        try:
            if path.exists():
                credentials = json.loads(secret_file(path))
                if credentials.get("refresh_token"):
                    request(
                        remote["domain"] + "/oauth2/revoke",
                        {
                            "client_id": remote["client_id"],
                            "token": credentials["refresh_token"],
                        },
                        form=True,
                    )
        finally:
            path.unlink(missing_ok=True)
            remote["signed_out"] = True
            save_config(store, config)
        return {"signed_out": True}
    if args.action == "resolve":
        report = store.cache / ("remote-" + args.name + "-conflicts.json")
        if not report.exists():
            raise MemoraError("No incoming conflict report exists.")
        incoming = json.loads(report.read_text())["incoming"]
        if args.id not in incoming:
            raise MemoraError("The report does not contain this identity.")
        entry = incoming[args.id]
        with store.lock():
            _, data, body = k.find(store, args.id)
            remote["baselines"][args.id] = {
                "revision": entry["revision"]
                if args.take == "local"
                else entry["revision"] - 1,
                "origin": entry["origin"],
                "fingerprint": k.fingerprint(data, body),
            }
            if args.take == "local":
                save_config(store, config)
        if args.take == "remote":
            apply_pull(store, args.name, remote, [{"entry": entry}], remote["cursor"])
        incoming.pop(args.id)
        if incoming:
            atomic(
                report,
                json.dumps(
                    {
                        "time": now(),
                        "incoming": incoming,
                        "reason": "Unresolved remote versions.",
                    }
                ),
            )
        else:
            report.unlink()
        return {
            "resolved": args.id,
            "selected": args.take,
            "publication": "A local change needs a new review before push.",
        }
    credential = token(store, args.name, remote)
    base = remote["url"] + "/v1/knowledge/spaces/" + remote["space"]
    if args.action == "references":
        try:
            identity = str(uuid.UUID(args.id))
        except ValueError as exc:
            raise MemoraError("Use a record UUID for reference resolution.") from exc
        return request(base + "/records/" + identity + "/references", token=credential)
    if args.action == "status":
        spaces = request(remote["url"] + "/v1/knowledge/spaces", token=credential)
        return {
            "connected": any(s["id"] == remote["space"] for s in spaces),
            "space": remote["space"],
            "cursor": remote["cursor"],
        }
    if args.action == "push":
        if remote.get("protocol") == "memora-knowledge-v1":
            from .standard import export_package

            package = export_package(store, remote["space"])
        else:
            package = export_v2(store, remote["space"])
        result = request(
            base + "/imports",
            {
                "package": package,
                "expected": {i: v["revision"] for i, v in remote["baselines"].items()},
                "publish": args.publish,
                "preview": args.preview,
            },
            credential,
        )
        if not args.preview:
            existing = {d["brain"]["id"]: (d, body) for _, d, body in k.notes(store)}
            for item in result["items"]:
                data, _body = existing[item["id"]]
                remote["baselines"][item["id"]] = {
                    "revision": item["revision"],
                    "origin": item["origin"],
                    "fingerprint": data["brain"]["publication"]["fingerprint"],
                }
            for record in package["records"]:
                if record["id"] in remote["baselines"]:
                    continue
                # A retry after a committed request can return only unchanged IDs.
                item = request(base + "/records/" + record["id"], token=credential)
                relations = [
                    edge
                    for edge in package["relations"]
                    if edge["origin"] == record["id"]
                ]
                if (
                    item.get("record") != record
                    or item.get("relations") != relations
                    or item.get("origin")
                    != record["origin"].get("brain", package["origin"])
                    or type(item.get("revision")) is not int
                    or item["revision"] < 1
                ):
                    raise Conflict(
                        "The committed remote content differs. Pull it for review."
                    )
                data, _ = existing[record["id"]]
                remote["baselines"][record["id"]] = {
                    "revision": item["revision"],
                    "origin": item["origin"],
                    "fingerprint": data["brain"]["publication"]["fingerprint"],
                }
            save_config(store, config)
        return result
    changes, cursor = [], remote["cursor"]
    while True:
        result = request(
            base + "/changes?" + urlencode({"since": cursor, "limit": 100}),
            token=credential,
        )
        if (
            not isinstance(result, dict)
            or not isinstance(result.get("items"), list)
            or type(result.get("cursor")) is not int
            or type(result.get("more")) is not bool
            or result["cursor"] < cursor
            or (result["more"] and result["cursor"] <= cursor)
        ):
            raise MemoraError("The remote change page does not advance a valid cursor.")
        changes.extend(result["items"])
        cursor = result["cursor"]
        if len(changes) > 10000:
            raise MemoraError(
                "The transfer exceeds 10000 changes. Select a smaller space."
            )
        if not result["more"]:
            break
    return apply_pull(store, args.name, remote, changes, cursor)
