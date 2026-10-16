"""Evaluate modeled, anonymized context tasks without an inference service."""

from pathlib import Path
import json
import tempfile
from memora import knowledge as k
from memora.service import MemoryService
from memora.store import Store


def evaluate():
    with tempfile.TemporaryDirectory(prefix="memora-context-eval-") as root:
        store = Store(Path(root))
        profile = store.create(
            {"type": "Profile", "title": "Work preferences"},
            "Use short updates. State the reason for a decision.",
            "human:example",
            "Keep preferences.",
        )
        subject = store.create(
            {
                "type": "Entity",
                "title": "Payment service",
                "brain": {"entity_kind": "service"},
            },
            "A service used by several applications.",
            "process:fixture",
            "Model a service task.",
        )
        observation = k.observe(
            store,
            title="Vendor support",
            subject=subject["path"],
            predicate="support_status",
            value="supported",
            basis="reported",
            sources=[{"resource": "https://example.org/vendor-support"}],
            actor="process:fixture",
            reason="Model a source finding.",
        )
        decision = store.create(
            {
                "type": "Decision",
                "title": "Local runtime access",
                "sources": [{"resource": "urn:example:runtime-check"}],
            },
            "Use explicit development settings for a local runtime. Reason: a local check must not require deployment credentials.",
            "process:fixture",
            "Model a previous implementation decision.",
        )
        checkpoint = store.create(
            {
                "type": "Checkpoint",
                "title": "Review service vendor concentration",
                "brain": {
                    "work_state": "in_progress",
                    "context": {"session": "previous"},
                },
            },
            "Next step: inspect service dependencies.",
            "process:fixture",
            "Model continuation in a new chat.",
        )
        cases = [
            ("Personal context", "start a different task", profile["path"], None),
            ("Previous decision", "local runtime access", decision["path"], None),
            ("Entity finding", "current support", observation["path"], subject["path"]),
            ("Task continuation", "vendor concentration", checkpoint["path"], None),
        ]
        results = []
        for name, query, target, entity in cases:
            packet = MemoryService(store).context(query, entity=entity)
            selected = [n["path"] for n in packet["notes"]]
            results.append(
                {
                    "case": name,
                    "found": target in selected,
                    "rank": selected.index(target) + 1 if target in selected else None,
                    "bytes": packet["bytes"],
                    "within_budget": packet["bytes"] <= packet["max_bytes"],
                }
            )
        return {
            "fixture": "Modeled from context and handoff tasks; no private corpus was exported.",
            "results": results,
            "passed": all(r["found"] and r["within_budget"] for r in results),
        }


if __name__ == "__main__":
    result = evaluate()
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["passed"] else 1)
