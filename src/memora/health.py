"""Build a review report from current evidence and graph data."""

from __future__ import annotations

from .index import Index

NON_FACT_TYPES = {"Idea", "Project", "Repository", "Task", "Checkpoint"}


def report(index: Index) -> dict:
    """Return review items. The checks suggest work; they do not confirm facts."""
    issues = []
    for node in index.all():
        path = node["path"]
        if node["stale"]:
            issues.append({"kind": "stale", "path": path, "title": node["title"]})
        if node["state"] == "provisional" and node["type"] not in NON_FACT_TYPES:
            issues.append({"kind": "provisional", "path": path, "title": node["title"]})
        if node["score"] < 50 and node["type"] not in NON_FACT_TYPES:
            issues.append(
                {
                    "kind": "low_evidence",
                    "path": path,
                    "title": node["title"],
                    "score": node["score"],
                    "reasons": node["reasons"],
                }
            )
        if "A contradiction is open." in node["reasons"]:
            issues.append(
                {"kind": "contradicted", "path": path, "title": node["title"]}
            )

    for edge in index.unknown_links():
        issues.append(
            {
                "kind": "missing_target",
                "path": edge["origin"],
                "target": edge["target"],
                "relation": edge["kind"],
            }
        )
    issues.sort(key=lambda item: (item["kind"], item["path"], item.get("target", "")))
    counts = {}
    for item in issues:
        counts[item["kind"]] = counts.get(item["kind"], 0) + 1
    return {"issues": issues, "counts": counts, "total": len(issues)}
