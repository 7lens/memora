"""Check the real CLI against a hermetic 7lens API on loopback with two local memories."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from memora import knowledge as k
from memora.codec import MemoraError
from memora.remote import request
from memora.store import Store, atomic


def check(sevenlens: Path) -> dict:
    root = Path(__file__).resolve().parents[1]
    environment = {**os.environ, "NEO4J_DISABLED": "1", "PYTHONPATH": str(root / "src")}
    server = subprocess.Popen(
        [
            str(sevenlens / "packages/api/node_modules/.bin/tsx"),
            "--conditions=development",
            "scripts/memora-connector-server.ts",
        ],
        cwd=sevenlens,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        if server.stdout is None:
            raise RuntimeError("No connector server output")
        line = server.stdout.readline()
        if not line:
            raise RuntimeError("The connector fixture did not start")
        url = "http://127.0.0.1:" + str(json.loads(line)["port"])
        with tempfile.TemporaryDirectory(prefix="memora-7lens-") as folder:
            source = Store(Path(folder) / "source")
            reader = Store(Path(folder) / "reader")
            tokens = {}
            for actor in ("alice", "bob", "bot"):
                path = Path(folder) / (actor + ".token")
                atomic(path, actor)
                tokens[actor] = str(path)
            space = request(
                url + "/v1/knowledge/spaces",
                {"name": "Protocol check", "kind": "team"},
                "alice",
            )
            base = url + "/v1/knowledge/spaces/" + space["id"]
            # Membership is a test fixture. No person receives a message or a real access grant.
            from urllib.request import Request, urlopen

            with urlopen(
                Request(
                    base + "/members",
                    method="PUT",
                    data=json.dumps(
                        {
                            "members": [
                                {
                                    "kind": "user",
                                    "subject": "alice",
                                    "role": "administrator",
                                },
                                {"kind": "user", "subject": "bob", "role": "reader"},
                                {
                                    "kind": "client",
                                    "subject": "bot",
                                    "role": "contributor",
                                },
                            ],
                            "revision": space["revision"],
                        }
                    ).encode(),
                    headers={
                        "Authorization": "Bearer alice",
                        "Content-Type": "application/json",
                    },
                ),
                timeout=10,
            ):
                pass

            def cli(store, *args, fails=False):
                value = subprocess.run(
                    [sys.executable, "-m", "memora", "--root", str(store.root), *args],
                    cwd=root,
                    env=environment,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
                if fails:
                    if value.returncode == 0:
                        raise AssertionError("A forbidden transfer succeeded")
                    return {"rejected": True}
                if value.returncode:
                    raise AssertionError(
                        "The real CLI check failed: " + value.stderr[:500]
                    )
                return json.loads(value.stdout)

            for store, actor in [(source, "alice"), (reader, "bob")]:
                cli(
                    store,
                    "remote",
                    "add",
                    "team",
                    "--url",
                    url,
                    "--space",
                    space["id"],
                    "--token-file",
                    tokens[actor],
                )
            note = source.create(
                {
                    "type": "Concept",
                    "title": "Connector policy",
                    "description": "A protocol fixture.",
                    "sources": [{"resource": "https://example.org/policy"}],
                    "brain": {
                        "external_refs": [
                            {
                                "provider": "7lens",
                                "instance": "local-development",
                                "entity_type": "service",
                                "entity_id": "compute.virtual_machines",
                                "relation": "documents",
                            }
                        ]
                    },
                },
                "Reviewed source context.",
                "agent:source",
                "Check source provenance.",
            )

            def approve():
                data, _ = source.read(note["path"])
                proposed = k.propose(
                    source,
                    note["path"],
                    data["brain"]["revision"],
                    space["id"],
                    "Review the fixture.",
                    "agent:fixture",
                )
                k.approve(
                    source,
                    note["path"],
                    proposed["revision"],
                    "human:fixture",
                    "Simulate fixture review.",
                )

            approve()
            cli(source, "remote", "push", "team", "--preview")
            assert request(base + "/records", token="bob")["items"] == []
            cli(source, "remote", "push", "team")
            assert cli(reader, "remote", "pull", "team")["received"] == 0
            cli(source, "remote", "push", "team", "--publish")
            assert cli(reader, "remote", "pull", "team")["received"] == 1
            path, data, body = k.find(reader, note["id"])
            assert body.strip() == "Reviewed source context."
            assert data["brain"]["provenance"]["created_by"] == "agent:source"
            from memora.standard import validate_package

            legacy = request(base + "/export", token="alice")
            standard = request(
                base + "/export?format=memora-knowledge-v1", token="alice"
            )
            assert validate_package(legacy)["profile"] == "legacy-v2"
            assert validate_package(standard)["profile"] == "exchange"
            assert "provenance" not in legacy["records"][0]
            assert (
                legacy["records"][0]["origin"]["brain"]
                == standard["records"][0]["origin"]["brain"]
            )
            references = cli(reader, "remote", "references", "team", "--id", note["id"])
            assert references[0]["status"] == "unavailable"
            assert "entity" not in references[0]
            assert cli(reader, "remote", "pull", "team")["received"] == 0
            # A machine cannot publish, even with a human label in the local projection.
            cli(
                source,
                "remote",
                "add",
                "machine",
                "--url",
                url,
                "--space",
                space["id"],
                "--token-file",
                tokens["bot"],
            )
            cli(source, "remote", "push", "machine", "--publish", fails=True)
            local = reader.update(
                path,
                {},
                "A concurrent local edit.",
                "agent:reader",
                "Check conflict preservation.",
                data["brain"]["revision"],
            )
            current, _ = source.read(note["path"])
            source.update(
                note["path"],
                {},
                "A new reviewed source revision.",
                "agent:source",
                "Check remote updates.",
                current["brain"]["revision"],
            )
            approve()
            cli(source, "remote", "push", "team", "--publish")
            cli(reader, "remote", "pull", "team", fails=True)
            assert reader.read(path)[0]["brain"]["revision"] == local["revision"]
            assert reader.read(path)[1].strip() == "A concurrent local edit."
            cli(
                reader,
                "remote",
                "resolve",
                "team",
                "--id",
                note["id"],
                "--take",
                "remote",
            )
            assert reader.read(path)[1].strip() == "A new reviewed source revision."
            entry = request(base + "/records/" + note["id"], token="alice")
            request(
                base + "/records/" + note["id"] + "/review",
                {"revision": entry["revision"], "state": "withdrawn"},
                "alice",
            )
            cli(reader, "remote", "pull", "team")
            assert reader.read(path)[0]["brain"]["state"] == "discarded"
            assert len(reader.history(path)) >= 4
            return {
                "passed": True,
                "protocol": "memora-knowledge-v1",
                "checks": [
                    "preview",
                    "draft isolation",
                    "human publication",
                    "provenance",
                    "idempotence",
                    "machine rejection",
                    "authorized reference boundary",
                    "cross-language exports",
                    "conflict preservation",
                    "explicit resolution",
                    "withdrawal history",
                ],
                "scope": "hermetic loopback API and real Python CLI; no live identity or graph deployment",
            }
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sevenlens", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(check(args.sevenlens.resolve()), indent=2))
    except (MemoraError, AssertionError, RuntimeError) as error:
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()
