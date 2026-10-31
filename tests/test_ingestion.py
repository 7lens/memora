"""Capture extracted conclusions without implicit publication or evidence checks."""

import copy
import hashlib
import subprocess

import pytest

from memora import knowledge as k
from memora.codec import Conflict, MemoraError
from memora.ingestion import ingest, repository_evidence
from memora.service import MemoryService


def findings():
    return {
        "format": "memora-findings-v1",
        "findings": [
            {
                "type": "Fact",
                "title": "Bounded context",
                "description": "Context has a size bound.",
                "body": "Context has a 12000 byte bound.",
                "reason": "Keep the finding.",
                "sources": [{"resource": "urn:example:context"}],
                "tags": ["context"],
            }
        ],
    }


def session(store):
    return MemoryService(store).context("context limits")["receipt"]["session_id"]


def test_preview_batch_and_replay_are_private_and_do_not_verify_sources(store):
    sid = session(store)
    assert ingest(store, sid, findings(), preview=True)["saved"] == 1
    assert list(k.notes(store)) == []
    result = ingest(store, sid, findings())
    assert result["saved"] == 1
    _, data, _ = list(k.notes(store))[0]
    assert data["brain"]["state"] == "provisional"
    assert data["brain"]["created_by"] == "agent:local-memory"
    assert "publication" not in data["brain"]
    assert "verified" not in data
    assert ingest(store, sid, findings())["results"][0]["state"] == "unchanged"
    modified = findings()
    modified["findings"][0]["body"] = "Another claim."
    assert ingest(store, sid, modified)["results"][0]["state"] == "needs_review"
    assert len(list(k.notes(store))) == 1


def test_invalid_later_finding_rolls_back_the_whole_batch(store):
    sid = session(store)
    document = findings()
    second = copy.deepcopy(document["findings"][0])
    second.update(type="Decision", title="Choice", body="No stated rationale.")
    document["findings"].append(second)
    with pytest.raises(MemoraError, match="reason"):
        ingest(store, sid, document)
    assert list(k.notes(store)) == []
    assert not list((store.bundle / "events").rglob("*.md"))


@pytest.mark.parametrize(
    "field,value",
    [
        ("body", "password=SuperSecret123"),
        ("body", "user: hello\nassistant: hello"),
        ("transcript", "raw conversation"),
        ("sources", [{"resource": "https://alice:secret@example.org/source"}]),
    ],
)
def test_capture_rejects_credentials_and_raw_chat_fields(store, field, value):
    sid = session(store)
    document = findings()
    document["findings"][0][field] = value
    with pytest.raises(MemoraError):
        ingest(store, sid, document)
    assert list(k.notes(store)) == []


def test_update_requires_the_current_revision(store):
    sid = session(store)
    saved = ingest(store, sid, findings())["results"][0]
    document = findings()
    document["findings"][0].update(
        path=saved["path"], revision=saved["revision"], body="Revised context bound."
    )
    assert ingest(store, sid, document)["saved"] == 1
    with pytest.raises(Conflict):
        ingest(store, sid, document)


def test_repository_evidence_contains_hash_and_revision_without_source_text(tmp_path):
    root = tmp_path / "repository"
    root.mkdir()
    subprocess.run(
        ["git", "init", "-b", "main", str(root)], check=True, capture_output=True
    )
    raw = b"Local source content.\r\n"
    (root / "policy.md").write_bytes(raw)
    subprocess.run(
        ["git", "-C", str(root), "add", "policy.md"], check=True, capture_output=True
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.org",
            "-c",
            "core.hooksPath=/dev/null",
            "commit",
            "-m",
            "Initial source",
        ],
        check=True,
        capture_output=True,
    )
    evidence = repository_evidence(root, "policy.md")
    assert evidence["sha256"] == hashlib.sha256(raw).hexdigest()
    assert evidence["sha256"] in evidence["resource"]
    assert evidence["revision"] in evidence["resource"]
    assert "Local source content" not in str(evidence)
    with pytest.raises(MemoraError):
        repository_evidence(root, "../outside")
    (root / ".env").write_text("TOKEN=private")
    with pytest.raises(MemoraError, match="tracked"):
        repository_evidence(root, ".env")


def test_interrupted_batch_recovers_notes_and_events_without_duplication(
    store, monkeypatch
):
    from memora import bundles

    sid = session(store)
    recover = bundles.recover_import

    def interrupt(_store):
        if (
            _store.root == store.root
            and (_store.cache / "import-transaction.json").exists()
        ):
            raise OSError("Simulated process interruption")
        return recover(_store)

    monkeypatch.setattr(bundles, "recover_import", interrupt)
    with pytest.raises(OSError):
        ingest(store, sid, findings())
    assert (store.cache / "import-transaction.json").exists()
    monkeypatch.setattr(bundles, "recover_import", recover)
    with store.lock():
        pass
    rows = list(k.notes(store))
    assert len(rows) == 1
    assert len(store.history(rows[0][0])) == 1
    assert ingest(store, sid, findings())["results"][0]["state"] == "unchanged"
