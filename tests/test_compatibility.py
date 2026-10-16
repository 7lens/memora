import json
import re
import tomllib
from pathlib import Path

import pytest

from memora import compatibility
from memora.cli import parser, run
from memora.codec import MemoraError
from memora.store import atomic


def test_package_version_matches_project_manifest():
    root = Path(__file__).resolve().parents[1]
    manifest = tomllib.loads((root / "pyproject.toml").read_text())
    assert manifest["project"]["version"] == compatibility.__version__


def test_changelog_defines_the_memory_action_for_each_release():
    root = Path(__file__).resolve().parents[1]
    releases = list(
        re.finditer(
            r"^## \[(\d+\.\d+\.\d+)\].*$", (root / "CHANGELOG.md").read_text(), re.M
        )
    )
    assert releases
    versions = [tuple(map(int, match.group(1).split("."))) for match in releases]
    assert ".".join(map(str, versions[0])) == compatibility.__version__
    for index, match in enumerate(releases):
        end = (
            releases[index + 1].start()
            if index + 1 < len(releases)
            else len((root / "CHANGELOG.md").read_text())
        )
        section = (root / "CHANGELOG.md").read_text()[match.start() : end]
        actions = re.findall(
            r"^- Memory action: `(baseline|none|reconsolidate)`\.$", section, re.M
        )
        assert len(actions) == 1
        if index == len(releases) - 1:
            assert actions[0] == "baseline"
            continue
        if match.group(1).split(".")[0] != releases[index + 1].group(1).split(".")[0]:
            assert actions[0] == "reconsolidate"
            assert "### Reconsolidation procedure" in section
        else:
            assert actions[0] == "none"


def test_first_note_sets_the_local_memory_version(store):
    store.create(
        {
            "type": "Fact",
            "title": "Versioned memory",
            "description": "A first note sets the tool baseline.",
            "tags": ["versioning"],
            "brain": {"state": "settled", "scope": "shared"},
        },
        "The baseline is local.",
        "process:test",
        "Create the first note.",
    )

    result = compatibility.status(store)
    assert result["memory_status"] == "compatible"
    assert result["memory_version"] == compatibility.__version__
    assert not result["reconsolidation_required"]


@pytest.mark.parametrize("version", ["1.0.1", "1.1.0", "1.9.99"])
def test_minor_and_patch_releases_do_not_require_reconsolidation(
    store, monkeypatch, version
):
    store.create(
        {"type": "Project", "title": "Memory", "tags": ["test"]},
        "",
        "process:test",
        "Create a project.",
    )
    monkeypatch.setattr(compatibility, "__version__", version)

    result = compatibility.status(store)
    assert result["memory_status"] == "compatible"
    assert not result["reconsolidation_required"]
    compatibility.assert_context_ready(store)


def test_major_release_blocks_context_until_reconciliation(store, monkeypatch):
    store.create(
        {"type": "Project", "title": "Memory", "tags": ["test"]},
        "",
        "process:test",
        "Create a project.",
    )
    monkeypatch.setattr(compatibility, "__version__", "2.0.0")

    result = compatibility.status(store)
    assert result["memory_status"] == "reconsolidation_required"
    with pytest.raises(MemoraError, match="CHANGELOG.md"):
        compatibility.assert_context_ready(store)


def test_context_cli_checks_version_before_reading_index(store, monkeypatch):
    from memora import cli

    store.create(
        {"type": "Project", "title": "Memory", "tags": ["test"]},
        "",
        "process:test",
        "Create a project.",
    )
    marker = compatibility.marker_path(store)
    atomic(
        marker,
        json.dumps({"format": 1, "tool_version": "2.0.0", "history": []}),
    )
    monkeypatch.setattr(compatibility, "__version__", "3.0.0")
    monkeypatch.setattr(cli, "Index", lambda _: pytest.fail("Index must not load."))
    args = parser().parse_args(
        ["--root", str(store.root), "context", "--query", "memory"]
    )

    with pytest.raises(MemoraError, match="CHANGELOG.md"):
        run(args)


def test_unmarked_existing_memory_blocks_context(store):
    marker = compatibility.marker_path(store)
    store.create(
        {"type": "Project", "title": "Memory", "tags": ["test"]},
        "",
        "process:test",
        "Create a project.",
    )
    marker.unlink()

    assert compatibility.status(store)["memory_status"] == "unmarked"
    with pytest.raises(MemoraError, match="unknown"):
        compatibility.assert_context_ready(store)


def test_reconcile_requires_valid_memory_then_records_migration(store):
    store.create(
        {
            "type": "Project",
            "title": "Memory",
            "tags": ["test"],
            "brain": {"state": "settled"},
        },
        "",
        "process:test",
        "Create a project.",
    )
    path = compatibility.marker_path(store)
    atomic(
        path,
        json.dumps(
            {
                "format": 1,
                "tool_version": "0.9.0",
                "history": [{"from": None, "to": "0.9.0"}],
            }
        ),
    )

    args = parser().parse_args(
        [
            "--root",
            str(store.root),
            "reconcile",
            "--reason",
            "Review the existing memory against the release procedure.",
        ]
    )
    result = run(args)

    assert result["reconciled"]
    assert result["memory_version"] == "0.9.0"
    assert result["tool_version"] == compatibility.__version__
    assert result["validation"]["valid"]
    assert compatibility.status(store)["memory_status"] == "compatible"


def test_reconcile_does_not_advance_memory_with_validation_warnings(store):
    store.create(
        {"type": "Project", "title": "Unclassified project"},
        "",
        "process:test",
        "Create an unclassified project.",
    )
    path = compatibility.marker_path(store)
    atomic(
        path,
        json.dumps({"format": 1, "tool_version": "0.9.0", "history": []}),
    )
    args = parser().parse_args(
        ["--root", str(store.root), "reconcile", "--reason", "Check the migration."]
    )

    with pytest.raises(MemoraError, match="validation error and warning"):
        run(args)
    assert compatibility.status(store)["memory_version"] == "0.9.0"


def test_context_blocks_when_checkout_has_newer_tool_version(store):
    (store.root / "pyproject.toml").write_text(
        f'[project]\nname = "memora"\nversion = "{compatibility.__version__.split(".")[0]}.99.0"\n'
    )
    with pytest.raises(MemoraError, match="Update "):
        compatibility.assert_context_ready(store)
