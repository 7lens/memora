from memora.health import report
from memora.index import Index


def test_health_lists_stale_provisional_and_unresolved_memory(store):
    note = store.create(
        {
            "type": "Fact",
            "title": "Unverified cache claim",
            "description": "A claim that needs a source.",
            "stale_after": "2020-01-01T00:00:00Z",
            "brain": {
                "state": "provisional",
                "relations": [{"type": "depends_on", "target": "/nodes/missing.md"}],
            },
        },
        "Review this claim.",
        "process:test",
        "Add a review candidate.",
    )
    index = Index(store)
    index.refresh()
    result = report(index)
    index.close()

    kinds = {item["kind"] for item in result["issues"] if item["path"] == note["path"]}
    assert kinds == {"stale", "provisional", "low_evidence", "missing_target"}
    assert result["counts"]["low_evidence"] == 1
    assert result["total"] == 4
