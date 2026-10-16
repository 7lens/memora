"""Keep existing memory readable after the project rename."""

import json
from pathlib import Path
import tomllib

from memora import compatibility
from memora.bundles import LEGACY_FORMAT, export_bundle, validate_bundle
from memora.cli import parser, root_path


def test_project_and_cli_use_memora():
    manifest = tomllib.loads(
        (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text()
    )
    assert manifest["project"]["name"] == "memora"
    assert manifest["project"]["scripts"] == {"memora": "memora.cli:main"}
    assert manifest["project"]["authors"] == [
        {"name": "Devidfirz", "email": "Devidfirz@7lens.io"}
    ]
    assert parser().prog == "memora"


def test_legacy_version_marker_keeps_its_history(store):
    previous = {
        "format": 1,
        "tool_version": "1.4.0",
        "history": [
            {
                "from": None,
                "to": "1.4.0",
                "actor": "process:fixture",
                "reason": "Original baseline.",
            }
        ],
    }
    legacy = store.bundle / compatibility.LEGACY_MARKER
    legacy.write_text(json.dumps(previous))
    assert compatibility.status(store)["memory_status"] == "compatible"
    assert not compatibility.marker_path(store).exists()
    store.create(
        {"type": "Concept", "title": "Retained context"},
        "Keep the context.",
        "process:test",
        "Check the renamed tool.",
    )
    assert json.loads(compatibility.marker_path(store).read_text()) == previous
    assert json.loads(legacy.read_text()) == previous


def test_private_bundle_uses_new_name_and_reads_previous_format(store, tmp_path):
    store.create(
        {"type": "Concept", "title": "Private context"},
        "Keep this local.",
        "process:test",
        "Create the fixture.",
    )
    output = tmp_path / "private.json"
    export_bundle(store, output)
    bundle = json.loads(output.read_text())
    assert bundle["format"] == "memora-private-v1"
    bundle["format"] = LEGACY_FORMAT
    validate_bundle(store, bundle)


def test_memora_root_environment_is_explicit(monkeypatch, tmp_path):
    monkeypatch.setenv("MEMORA_ROOT", str(tmp_path))
    assert root_path(parser().parse_args(["version"])) == tmp_path
