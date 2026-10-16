from memora.cli import parser, run


def checkpoint_args(store, repository, session, progress, extra=()):
    args = [
        "--root",
        str(store.root),
        "checkpoint",
        "--session",
        session,
        "--repository",
        repository,
        "--goal",
        "Compare two tools.",
        "--progress",
        progress,
        "--next",
        "Review the result.",
        "--reason",
        "Record task progress.",
        *extra,
    ]
    return parser().parse_args(args)


def test_checkpoint_keeps_candidates_and_ideas_across_updates(store):
    repository = store.create(
        {"type": "Repository", "title": "Test repository"},
        "",
        "process:test",
        "Register the repository.",
    )["path"]
    first = checkpoint_args(
        store,
        repository,
        "session-1",
        "Read both designs.",
        (
            "--candidate",
            "SQLite FTS5 is the current search index.",
            "--idea",
            "Review semantic search.",
        ),
    )
    created = run(first)
    assert created["revision"] == 1

    second = checkpoint_args(
        store,
        repository,
        "session-1",
        "Compare the search tools.",
        ("--revision", "1", "--candidate", "The other tool uses BM25 and LSA."),
    )
    updated = run(second)
    assert updated["revision"] == 2

    _, body = store.read(created["path"])
    assert "SQLite FTS5 is the current search index." in body
    assert "The other tool uses BM25 and LSA." in body
    assert "Review semantic search." in body
    log = (store.bundle / "log.md").read_text(encoding="utf-8")
    assert log.endswith(".\n")
    assert not log.endswith("\n\n")
