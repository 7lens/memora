import time
from pathlib import Path

import pytest
from memora.codec import dump
from memora.context import packet
from memora.index import Index
from memora.viewer import data as viewer_data


@pytest.mark.scale
def test_10000_notes_selective_reads_and_live_view_data(store):
    directory = store.bundle / "nodes"
    directory.mkdir()
    for i in range(10000):
        relations = (
            [{"type": "related_to", "target": f"/nodes/item-{i - 1}.md"}] if i else []
        )
        from memora.codec import render_relations

        data = {
            "type": "Concept",
            "title": f"Item {i}",
            "description": "A cache concept." if i < 10 else "A source concept.",
            "brain": {"state": "provisional", "revision": 1, "relations": relations},
        }
        (directory / f"item-{i}.md").write_text(
            dump(data, render_relations("", relations))
        )
    idx = Index(store)
    start = time.monotonic()
    idx.refresh()
    assert idx.read_count == 10000
    cold = time.monotonic() - start
    idx.read_count = 0
    start = time.monotonic()
    idx.refresh()
    assert idx.read_count == 0
    assert len(idx.search("cache")) == 10
    text = packet(idx, "cache", Path("/tmp"))
    assert len(text.encode()) <= 12000
    warm = time.monotonic() - start
    graph = viewer_data(idx, live=True)
    assert len(graph["nodes"]) == 10000 and len(graph["edges"]) == 9999
    print(
        f"\nScale: cold={cold:.3f}s warm={warm:.3f}s nodes={len(graph['nodes'])} edges={len(graph['edges'])}"
    )
    idx.close()
