import json
import subprocess
import sys
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from memora.codec import MemoraError
from memora.cli import parser, run, validate
from memora.index import Index
from memora.integrations import doctor, install, uninstall
from memora.language import check
from memora.live import make_server
from memora.viewer import data as viewer_data, render_data


def test_install_preserves_files_and_uninstall_is_exact(store, tmp_path):
    home = tmp_path / "home"
    original = home / ".codex/AGENTS.md"
    original.parent.mkdir(parents=True)
    original.write_text("Existing rules.\n")
    before = original.read_bytes()
    first = install(store, home)
    assert len(first) == 5
    second = install(store, home)
    assert all(not r["changed"] for r in second)
    assert original.read_text().startswith("Existing rules.")
    assert "review all turns and attachments" in original.read_text()
    assert "Record any context you cannot access." in original.read_text()
    assert all(r["pointer_present"] for r in doctor(store, home)["editors"])
    uninstall(store, home)
    assert original.read_bytes() == before
    assert not (home / ".kiro/steering/memora.md").exists()
    assert not (home / ".config/memora/config.json").exists()


def test_codex_override_receives_pointer(store, tmp_path):
    home = tmp_path / "home"
    override = home / ".codex/AGENTS.override.md"
    override.parent.mkdir(parents=True)
    override.write_text("Override rules.\n")
    install(store, home, "codex")
    assert "<!-- memora:start -->" in override.read_text()
    assert not (home / ".codex/AGENTS.md").exists()


def test_install_dry_run_has_no_files(store, tmp_path):
    home = tmp_path / "home"
    assert len(install(store, home, dry_run=True)) == 5
    assert not home.exists()


def test_install_refuses_another_brain_before_changes(store, tmp_path):
    home = tmp_path / "home"
    config = home / ".config/memora/config.json"
    config.parent.mkdir(parents=True)
    config.write_text(json.dumps({"root": "/some/other/brain"}))
    with pytest.raises(MemoraError):
        install(store, home)
    assert not (home / ".codex").exists()


def test_uninstall_preserves_later_user_edits(store, tmp_path):
    home = tmp_path / "home"
    install(store, home, "codex")
    path = home / ".codex/AGENTS.md"
    path.write_text(path.read_text() + "\nA later rule.\n")
    uninstall(store, home, "codex")
    assert "A later rule." in path.read_text()
    assert "memora:start" not in path.read_text()


def test_language_reports_partial_coverage_and_grammar(store):
    result = check(
        "Utilize this tool. The file was changed. Do not use this sentence "
        + "word " * 30
        + ".",
        store.root,
    )
    rules = {i["rule"] for i in result["issues"]}
    assert result["coverage"] == "partial"
    assert result["result"] == "needs_review"
    assert {"vocabulary", "possible_passive", "sentence_length"} <= rules
    assert "do not certify" in result["notice"]


def test_source_quotes_and_code_keep_original_words(store):
    result = check(
        "Use the tool.\n\n> Utilize this tool.\n\n```\ncommence();\n```\nUse `leverage()`.",
        store.root,
    )
    assert not any(i["rule"] == "vocabulary" for i in result["issues"])


def test_dictionary_and_glossary_are_separate(store, tmp_path):
    dictionary = tmp_path / "dict.json"
    dictionary.write_text(
        json.dumps({"issue": 9, "complete": False, "words": {"use": {}, "the": {}}})
    )
    result = check("Use the knowledge graph.", store.root, dictionary=dictionary)
    assert result["issues"] == []
    assert result["coverage"] == "partial"
    result = check("Use the unlistedword.", store.root, dictionary=dictionary)
    assert result["issues"][0]["rule"] == "unlisted_word"


def test_live_view_escapes_note_content_and_has_no_body(store):
    malicious = "</script><script>window.INJECTED=true</script>"
    store.create(
        {"type": "Idea", "title": malicious, "description": "A short description."},
        "BODY_NOT_FOR_EXPORT",
        "process:test",
        "Inspect safe display.",
    )
    idx = Index(store)
    idx.refresh()
    text = render_data(viewer_data(idx, live=True))
    assert malicious not in text
    assert "\\u003c/script\\u003e" in text
    assert "BODY_NOT_FOR_EXPORT" not in text
    assert "connect-src 'self'" in text
    assert 'id="subject"' not in text
    idx.close()


def test_cli_smoke_and_conflict(store, tmp_path):
    def cli(*args):
        return subprocess.run(
            [sys.executable, "-m", "memora", "--root", str(store.root), *args],
            capture_output=True,
            text=True,
            check=False,
        )

    project = cli("register", "project", "--name", "Sample")
    assert project.returncode == 0
    project_path = json.loads(project.stdout)["path"]
    capture = cli(
        "capture",
        "--type",
        "Idea",
        "--title",
        "Cache",
        "--description",
        "Use a cache.",
        "--project",
        project_path,
        "--reason",
        "Keep the idea.",
    )
    assert capture.returncode == 0
    path = json.loads(capture.stdout)["path"]
    assert "Cache" in cli("search", "cache").stdout
    assert (
        cli(
            "transition",
            path,
            "--revision",
            "1",
            "--state",
            "settled",
            "--reason",
            "Accept the idea.",
        ).returncode
        == 0
    )
    assert (
        cli(
            "transition",
            path,
            "--revision",
            "1",
            "--state",
            "discarded",
            "--reason",
            "Reject the idea.",
        ).returncode
        == 3
    )
    assert json.loads(cli("validate").stdout)["valid"]
    assert cli("export").returncode != 0


def test_capture_merges_metadata_without_losing_classification(store, tmp_path):
    project_a = store.create(
        {"type": "Project", "title": "Project A"}, "", "process:test", "Add A."
    )
    project_b = store.create(
        {"type": "Project", "title": "Project B"}, "", "process:test", "Add B."
    )
    repository = store.create(
        {"type": "Repository", "title": "Repository A"}, "", "process:test", "Add repo."
    )
    target = store.create(
        {"type": "Fact", "title": "Source fact"}, "", "process:test", "Add fact."
    )
    metadata = tmp_path / "metadata.json"
    metadata.write_text(
        json.dumps(
            {
                "tags": ["security"],
                "sources": [{"resource": "conversation:one"}],
                "brain": {
                    "state": "settled",
                    "projects": [project_a["path"]],
                    "repositories": [repository["path"]],
                    "relations": [{"type": "supports", "target": target["path"]}],
                    "context": {"session": "keep-me"},
                    "extra": "preserve-me",
                },
            }
        )
    )
    result = run(
        parser().parse_args(
            [
                "--root",
                str(store.root),
                "capture",
                "--type",
                "Decision",
                "--title",
                "Captured decision",
                "--description",
                "A captured decision.",
                "--metadata",
                str(metadata),
                "--tag",
                "access",
                "--source",
                "conversation:two",
                "--project",
                project_b["path"],
                "--relation",
                "related_to:" + target["path"],
                "--reason",
                "Keep metadata values.",
            ]
        )
    )
    data, _ = store.read(result["path"])
    assert data["tags"] == ["security", "access"]
    assert [source["resource"] for source in data["sources"]] == [
        "conversation:one",
        "conversation:two",
    ]
    assert data["brain"]["state"] == "settled"
    assert data["brain"]["projects"] == [project_a["path"], project_b["path"]]
    assert data["brain"]["repositories"] == [repository["path"]]
    assert data["brain"].get("scope") is None
    assert data["brain"]["context"]["session"] == "keep-me"
    assert data["brain"]["extra"] == "preserve-me"
    assert {(r["type"], r["target"]) for r in data["brain"]["relations"]} == {
        ("supports", target["path"]),
        ("related_to", target["path"]),
    }


def test_validate_reports_missing_subject_and_scope(store):
    store.create(
        {"type": "Fact", "title": "Unclassified fact"}, "", "process:test", "Add it."
    )
    result = validate(store)
    messages = " ".join(warning["message"] for warning in result["warnings"])
    assert result["valid"] is True
    assert "subject tags" in messages
    assert "Scope is pending" in messages


def test_capture_code_finding_adds_registered_repository_scope(store, tmp_path):
    repository_root = tmp_path / "source"
    repository_root.mkdir()
    subprocess.run(
        ["git", "init", str(repository_root)], check=True, capture_output=True
    )
    (repository_root / "source.txt").write_text("source\n")
    subprocess.run(
        ["git", "-C", str(repository_root), "add", "source.txt"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(repository_root),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "-c",
            "core.hooksPath=/dev/null",
            "commit",
            "-m",
            "Source",
        ],
        check=True,
        capture_output=True,
    )
    registered = run(
        parser().parse_args(
            [
                "--root",
                str(store.root),
                "register",
                "repository",
                "--name",
                "Source",
                "--cwd",
                str(repository_root),
            ]
        )
    )
    captured = run(
        parser().parse_args(
            [
                "--root",
                str(store.root),
                "capture",
                "--type",
                "Fact",
                "--title",
                "Code fact",
                "--description",
                "A code finding.",
                "--code-cwd",
                str(repository_root),
                "--source",
                "/source.txt",
                "--tag",
                "code",
                "--reason",
                "Record its revision.",
            ]
        )
    )
    data, _ = store.read(captured["path"])
    assert registered["path"].startswith("/repositories/")
    assert data["brain"]["repositories"] == [registered["path"]]
    assert data["brain"]["context"]["revision"]
    assert data["brain"]["context"]["branch"] is not None


def test_relation_types_need_a_catalog_definition(store):
    store.create(
        {
            "type": "Idea",
            "title": "New relation",
            "brain": {"relations": [{"type": "implies", "target": "/nodes/target.md"}]},
        },
        "",
        "process:test",
        "Test a custom relation.",
    )
    result = validate(store)
    assert result["valid"] is False
    assert any("docs/relations.md" in error["message"] for error in result["errors"])


def test_belongs_to_must_target_a_scope_entity(store):
    target = store.create(
        {"type": "Fact", "title": "Not a scope"}, "", "process:test", "Add a fact."
    )
    store.create(
        {
            "type": "Decision",
            "title": "Bad membership",
            "brain": {"relations": [{"type": "belongs_to", "target": target["path"]}]},
        },
        "",
        "process:test",
        "Test relation semantics.",
    )
    result = validate(store)
    assert result["valid"] is False
    assert any(
        "must target a project or repository" in error["message"]
        for error in result["errors"]
    )


def test_viewer_links_safe_sources_and_registered_repository_files(store, tmp_path):
    repository_root = tmp_path / "source"
    repository_root.mkdir()
    source_file = repository_root / "source.txt"
    source_file.write_text("source\n")
    repository_path = "/repositories/source.md"
    store.create(
        {"type": "Repository", "title": "Source"},
        "",
        "process:test",
        "Register a source repository.",
        repository_path,
    )
    store.cache.joinpath("config.json").write_text(
        json.dumps({"repositories": {repository_path: {"root": str(repository_root)}}})
    )
    store.create(
        {
            "type": "Fact",
            "title": "Source links",
            "sources": [
                {"resource": "/source.txt"},
                {"resource": "https://example.com/source"},
                {"resource": "javascript:alert(1)"},
            ],
            "brain": {"repositories": [repository_path]},
        },
        "",
        "process:test",
        "Check source links.",
    )
    index = Index(store)
    index.refresh()
    html = render_data(viewer_data(index, live=True))
    index.close()

    assert source_file.resolve().as_uri() in html
    assert '"href": "https://example.com/source"' in html
    assert '"href": "javascript:alert(1)"' not in html


def test_live_view_reads_repository_changes_and_supports_etags(store):
    store.create(
        {"type": "Fact", "title": "First live note"},
        "",
        "process:test",
        "Add the first live note.",
    )
    server = make_server(store.root)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(base + "/") as response:
            page = response.read().decode()
        assert '"live": true' in page

        with urlopen(base + "/api/data") as response:
            initial = json.load(response)
            etag = response.headers["ETag"]
        assert any(note["title"] == "First live note" for note in initial["nodes"])
        try:
            urlopen(Request(base + "/api/data", headers={"Host": "example.invalid"}))
            raise AssertionError("The live view must reject other Host values.")
        except HTTPError as error:
            assert error.code == 403
        try:
            urlopen(Request(base + "/api/data", headers={"If-None-Match": etag}))
            raise AssertionError("The unchanged graph must return HTTP 304.")
        except HTTPError as error:
            assert error.code == 304

        store.create(
            {"type": "Fact", "title": "New repository note"},
            "",
            "process:test",
            "Add a note while the view is open.",
        )
        with urlopen(
            Request(base + "/api/data", headers={"If-None-Match": etag})
        ) as response:
            updated = json.load(response)
        assert updated["version"] != initial["version"]
        assert any(note["title"] == "New repository note" for note in updated["nodes"])
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_view_command_dispatches_to_local_live_server(store, monkeypatch):
    from memora import live

    monkeypatch.setattr(
        live,
        "view",
        lambda root, no_open: {"root": str(root), "no_open": no_open},
    )
    result = run(parser().parse_args(["--root", str(store.root), "view", "--no-open"]))
    assert result == {"root": str(store.root), "no_open": True}


def test_language_softbreaks_do_not_merge_words_or_sentences(store):
    from memora.language import prose

    text = "Keep the source\nreference. Read the note.\n\n> Keep this quote unchanged."
    assert "source reference." in prose(text)
    assert "Keep this quote" not in prose(text)
    assert not any(
        i["rule"] == "sentence_length" for i in check(text, store.root)["issues"]
    )
