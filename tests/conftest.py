import shutil
from pathlib import Path

import pytest
from memora.store import Store


@pytest.fixture
def store(tmp_path):
    root = tmp_path / "brain"
    root.mkdir()
    source = Path(__file__).resolve().parents[1]
    shutil.copytree(source / "docs", root / "docs")
    shutil.copy(source / "START.md", root / "START.md")
    return Store(root)


@pytest.fixture
def note(store):
    return store.create(
        {
            "type": "Fact",
            "title": "Cache reads",
            "description": "The cache reduces repeated reads.",
        },
        "Use a source check before the change.",
        "codex/unknown",
        "Keep the source claim.",
    )
