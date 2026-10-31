"""Conformance at the Markdown, linked data, and reviewed exchange boundaries."""

import copy
import json

import pytest
from jsonschema import Draft202012Validator

from memora import knowledge as k, standard as s
from memora.bundles import export_bundle
from memora.codec import Conflict, MemoraError
from memora.remote import export_v2, seal
from memora.store import Store, atomic


def reviewed(store, kind="Concept", title="Cache policy", body="Use bounded reads."):
    note = store.create(
        {
            "type": kind,
            "title": title,
            "description": "Cache policy.",
            "sources": [
                {"resource": "https://example.org/policy"},
                {"resource": "/private/notes.md"},
            ],
        },
        body,
        "agent:author",
        "Keep the policy.",
    )
    proposal = k.propose(
        store,
        note["path"],
        note["revision"],
        "team",
        "Review the policy.",
        "agent:author",
    )
    k.approve(
        store,
        note["path"],
        proposal["revision"],
        "human:alice",
        "Approve the exact content.",
    )
    return note


def test_schemas_compile_and_unknown_markdown_fields_survive(store):
    for name in s.SCHEMAS:
        Draft202012Validator.check_schema(s.schema(name))
    note = reviewed(store)
    data, body = store.read(note["path"])
    data["custom"] = {"keep": ["unknown", 7]}
    s.validate_schema(data, "note")
    assert body.strip() == "Use bounded reads."


def test_jsonld_round_trip_has_distinct_provenance_and_review(store):
    reviewed(store)
    package = s.export_package(store, "team")
    assert s.validate_package(package)["records"] == 1
    document = s.to_jsonld(package)
    assert s.from_jsonld(json.loads(json.dumps(document))) == package
    nodes = document["@graph"]
    entity = next(
        n for n in nodes if isinstance(n["type"], list) and "prov:Entity" in n["type"]
    )
    review = next(
        n for n in nodes if isinstance(n["type"], list) and "prov:Activity" in n["type"]
    )
    assert entity["author"] == "urn:memora:actor:agent%3Aauthor"
    assert review["reviewed_by"] == "urn:memora:actor:human%3Aalice"
    assert "/private/" not in json.dumps(package)
    assert "verified" not in json.dumps(document)
    assert entity["source"] == ["https://example.org/policy"]
    altered = copy.deepcopy(document)
    altered["@graph"][1]["title"] = "A false view"
    with pytest.raises(MemoraError, match="semantic view"):
        s.from_jsonld(altered)
    altered = copy.deepcopy(document)
    altered["@context"] = "https://example.org/untrusted-context"
    with pytest.raises(MemoraError, match="pinned"):
        s.from_jsonld(altered)


def test_independent_rdf_processor_reads_semantic_relations_and_provenance():
    from pathlib import Path
    from rdflib import Graph, Namespace, URIRef, RDF

    root = Path(__file__).resolve().parents[1]
    package = s.read_document(root / "examples/standard/team.json")
    document = s.read_document(root / "examples/standard/team.jsonld")
    assert package == document
    graph = Graph().parse(data=json.dumps(s.to_jsonld(package)), format="json-ld")
    prov = Namespace("http://www.w3.org/ns/prov#")
    memora = Namespace("urn:memora:")
    assert len(list(graph.subjects(RDF.type, prov.Entity))) == 2
    assert len(list(graph.subjects(RDF.type, prov.Activity))) == 2
    assert (
        URIRef(s.uri(package["relations"][0]["origin"])),
        memora.documents,
        URIRef(s.uri(package["relations"][0]["target"])),
    ) in graph
    assert (
        len(
            list(
                graph.triples(
                    (None, prov.wasDerivedFrom, URIRef("https://example.org/design"))
                )
            )
        )
        == 2
    )


def test_private_vault_requires_no_publication_and_omits_activity(store, tmp_path):
    note = store.create(
        {"type": "Concept", "title": "Private concept", "description": "Private."},
        "Local knowledge.",
        "agent:a",
        "Keep a concept.",
    )
    store.create(
        {"type": "Profile", "title": "Private preferences"},
        "A personal preference.",
        "agent:a",
        "Keep preferences.",
    )
    output = tmp_path / "private-vault"
    s.export_private_vault(store, output)
    manifest = json.loads((output / "memora-export.json").read_text())
    assert manifest["privacy"] == "private"
    assert [record["id"] for record in manifest["records"]] == [note["id"]]
    assert "publication" not in manifest["records"][0]["metadata"]["brain"]


def test_reviewed_import_retains_content_ids_sources_and_provenance(store, tmp_path):
    note = reviewed(store)
    package = s.export_package(store, "team")
    source = tmp_path / "standard.jsonld"
    source.write_text(json.dumps(s.to_jsonld(package)))
    target = Store(tmp_path / "target")
    atomic(
        target.cache / "workspace.json",
        json.dumps({"id": "team", "name": "team", "kind": "team"}),
    )
    assert s.import_document(target, source)["imported"] == 1
    assert s.import_document(target, source)["unchanged"] == 1
    _, metadata, body = k.find(target, note["id"])
    assert body.strip() == package["records"][0]["body"]
    assert metadata["brain"]["provenance"] == package["records"][0]["provenance"]
    assert metadata["brain"]["shared_origin"]["brain"] == package["origin"]
    assert not metadata.get("verified")
    assert not metadata["brain"].get("publication")
    target.update(
        "/nodes/" + note["id"] + ".md",
        {},
        "Local change.",
        "agent:local",
        "Keep an edit.",
        metadata["brain"]["revision"],
    )
    with pytest.raises(Conflict):
        s.import_document(target, source)


@pytest.mark.parametrize(
    "change", ["version", "checksum", "duplicate", "private", "subject", "kind"]
)
def test_rejects_invalid_packages_before_import(store, change):
    reviewed(store)
    package = s.export_package(store, "team")
    if change == "version":
        package["version"] = "2.0.0"
    elif change == "checksum":
        package["records"][0]["body"] += "tamper"
    elif change == "duplicate":
        package["records"].append(copy.deepcopy(package["records"][0]))
        package = seal(package)
    elif change == "private":
        package["records"][0]["type"] = "Profile"
        package = seal(package)
    elif change == "subject":
        package["records"][0]["observation"] = {
            "subject": {"id": package["origin"], "kind": "entity"},
            "predicate": "status",
            "value": "up",
            "basis": "inferred",
            "author": "agent:a",
            "observed_at": "2026-10-31T10:00:00Z",
        }
        package["records"][0]["type"] = "Observation"
        package = seal(package)
    else:
        package["records"][0]["type"] = "Anything"
        package = seal(package)
    with pytest.raises(MemoraError):
        s.validate_package(package)


def test_vault_links_are_resolvable_and_output_is_not_overwritten(store, tmp_path):
    a = reviewed(store, title="First")
    b = reviewed(store, title="Second")
    data, _ = store.read(a["path"])
    edge = k.relate(
        store,
        a["id"],
        b["id"],
        "depends_on",
        data["brain"]["revision"],
        "agent:a",
        "Keep a dependency.",
    )
    proposal = k.propose(
        store,
        a["path"],
        edge["revision"],
        "team",
        "Review the new relation.",
        "agent:a",
    )
    k.approve(
        store, a["path"], proposal["revision"], "human:alice", "Review the relation."
    )
    package = s.export_package(store, "team")
    path = tmp_path / "vault"
    s.export_vault(store, package, path)
    assert (path / (b["id"] + ".md")).exists()
    assert f"({b['id']}.md)" in (path / (a["id"] + ".md")).read_text()
    assert json.loads((path / "memora-export.json").read_text()) == package
    with pytest.raises(MemoraError):
        s.export_vault(store, package, path)


def test_legacy_and_private_profiles_keep_their_contracts(store, tmp_path):
    note = reviewed(store)
    assert s.validate_package(k.export_shared(store, "team"))["profile"] == "legacy-v1"
    assert s.validate_package(export_v2(store, "team"))["profile"] == "legacy-v2"
    assert "provenance" not in export_v2(store, "team")["records"][0]
    data, _ = store.read(note["path"])
    store.update(
        note["path"],
        {"unknown": {"data": [1, 2]}},
        None,
        "agent:a",
        "Keep extension fields.",
        data["brain"]["revision"],
    )
    path = tmp_path / "private.json"
    export_bundle(store, path)
    assert s.validate_file(store, path)["profile"] == "private"
    target = Store(tmp_path / "target")
    s.import_document(target, path)
    assert (
        target.path(note["path"]).read_bytes() == store.path(note["path"]).read_bytes()
    )
    assert target.history(note["path"]) == store.history(note["path"])


def test_republished_import_preserves_source_identity_and_does_not_invent_an_author(
    store, tmp_path
):
    from memora.codec import json_text

    original = reviewed(store)
    value = s.export_package(store, "team")
    value["records"][0].pop("provenance")
    value = seal(value)
    path = tmp_path / "legacy-origin.json"
    path.write_text(json_text(value))
    target = Store(tmp_path / "target")
    atomic(
        target.cache / "workspace.json",
        json.dumps({"id": "team", "name": "team", "kind": "team"}),
    )
    s.import_document(target, path)
    key, metadata, _ = k.find(target, original["id"])
    p = k.propose(
        target,
        key,
        metadata["brain"]["revision"],
        "another-team",
        "Share the origin.",
        "agent:importer",
    )
    k.approve(
        target, key, p["revision"], "human:fixture", "Review the imported content."
    )
    exported = s.export_package(target, "another-team")
    assert exported["records"][0]["origin"]["brain"] == value["origin"]
    assert "provenance" not in exported["records"][0]
    metadata, _ = target.read(key)
    changed = target.update(
        key,
        {},
        "A local contribution.",
        "agent:contributor",
        "Add local knowledge.",
        metadata["brain"]["revision"],
    )
    p = k.propose(
        target,
        key,
        changed["revision"],
        "another-team",
        "Share the contribution.",
        "agent:contributor",
    )
    k.approve(target, key, p["revision"], "human:fixture", "Review the contribution.")
    provenance = s.export_package(target, "another-team")["records"][0]["provenance"]
    assert "created_by" not in provenance
    assert provenance["updated_by"] == "agent:contributor"


def test_private_recovery_does_not_rebind_existing_remote_ownership(store, tmp_path):
    reviewed(store)
    before = s.export_package(store, "team")
    source = tmp_path / "private-recovery.json"
    export_bundle(store, source)
    restored = Store(tmp_path / "restored")
    s.import_document(restored, source)
    after = s.export_package(restored, "team")
    assert before["origin"] != after["origin"]
    assert before["records"][0]["id"] == after["records"][0]["id"]
    assert (
        before["records"][0]["origin"]["brain"]
        == after["records"][0]["origin"]["brain"]
    )
    assert (
        export_v2(restored, "team")["records"][0]["origin"]["brain"]
        == before["records"][0]["origin"]["brain"]
    )


def test_reviewed_import_retains_expiry_in_local_context_checks(store, tmp_path):
    from memora.codec import score

    note = store.create(
        {
            "type": "Fact",
            "title": "Expired policy",
            "description": "A dated policy.",
            "sources": [{"resource": "https://example.org/policy"}],
            "stale_after": "2020-01-01T00:00:00Z",
        },
        "Check the current source before use.",
        "agent:source",
        "Keep the dated claim.",
    )
    proposed = k.propose(
        store,
        note["path"],
        note["revision"],
        "team",
        "Review the dated claim.",
        "agent:source",
    )
    k.approve(
        store,
        note["path"],
        proposed["revision"],
        "human:fixture",
        "Review the fixture.",
    )
    source = tmp_path / "dated.json"
    source.write_text(json.dumps(s.export_package(store, "team")))
    target = Store(tmp_path / "target")
    atomic(
        target.cache / "workspace.json",
        json.dumps({"id": "team", "name": "team", "kind": "team"}),
    )
    s.import_document(target, source)
    _, metadata, body = k.find(target, note["id"])
    assert metadata["stale_after"] == "2020-01-01T00:00:00Z"
    assert score(metadata, body, at="2026-10-31T00:00:00Z")["stale"] is True
