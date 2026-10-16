import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

from memora.cli import register
from memora.context import current_repository, packet, remote_id, repo_identity
from memora.index import Index


def test_scope_budget_and_retired_notes(store):
    a = store.create(
        {"type": "Project", "title": "Project A"},
        "",
        "process:test",
        "Add the project.",
    )
    b = store.create(
        {"type": "Project", "title": "Project B"},
        "",
        "process:test",
        "Add the project.",
    )
    r = store.create(
        {"type": "Repository", "title": "Repo A", "brain": {"projects": [a["path"]]}},
        "",
        "process:test",
        "Add the repository.",
    )
    own = store.create(
        {
            "type": "Fact",
            "title": "Cache own",
            "description": "Use a cache.",
            "brain": {"repositories": [r["path"]]},
        },
        "",
        "process:test",
        "Add the fact.",
    )
    foreign = store.create(
        {
            "type": "Fact",
            "title": "Cache secret",
            "description": "A private project result.",
            "brain": {"projects": [b["path"]]},
        },
        "",
        "process:test",
        "Add the fact.",
    )
    retired = store.create(
        {"type": "Idea", "title": "Cache retired", "brain": {"state": "discarded"}},
        "",
        "process:test",
        "Keep the old idea.",
    )
    idx = Index(store)
    idx.refresh()
    text = packet(idx, "cache", Path("/tmp"), repository=r["path"])
    assert (
        own["path"] in text
        and foreign["path"] not in text
        and retired["path"] not in text
    )
    assert "Project A" in text
    small = packet(idx, "cache", Path("/tmp"), repository=r["path"], max_bytes=512)
    assert len(small.encode()) <= 512
    assert "omitted" in small
    idx.close()


def test_unicode_context_budget(store):
    for i in range(10):
        store.create(
            {"type": "Concept", "title": "Memory " + str(i), "description": "é" * 200},
            "",
            "process:test",
            "Keep the concept.",
        )
    idx = Index(store)
    idx.refresh()
    result = packet(idx, "Memory", Path("/tmp"), max_bytes=2000)
    assert len(result.encode("utf-8")) <= 2000
    idx.close()


def test_checkpoints_do_not_cross_sessions(store):
    repo = store.create(
        {"type": "Repository", "title": "Source"},
        "",
        "process:test",
        "Register the source.",
    )
    for session in ["one", "two"]:
        store.create(
            {
                "type": "Checkpoint",
                "title": "Task " + session,
                "description": "Cache work",
                "brain": {
                    "repositories": [repo["path"]],
                    "context": {"session": session},
                },
            },
            "Continue with the source check.",
            "process:test",
            "Keep progress.",
        )
    idx = Index(store)
    idx.refresh()
    result = packet(idx, "cache", Path("/tmp"), repository=repo["path"], session="one")
    assert "Task one" in result and "Task two" not in result
    idx.close()


def test_repo_normalization_removes_credentials():
    assert remote_id("git@github.com:org/repo.git") == "github.com/org/repo"
    assert (
        remote_id("https://user:secret@github.com/org/repo.git")
        == "github.com/org/repo"
    )


def git(cwd, *args):
    result = subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def test_registered_worktrees_and_same_names(store, tmp_path):
    root = tmp_path / "first" / "app"
    root.mkdir(parents=True)
    git(root, "init")
    (root / "a").write_text("a")
    git(root, "add", "a")
    git(
        root,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "-c",
        "core.hooksPath=/dev/null",
        "commit",
        "-m",
        "Test",
    )
    worktree = tmp_path / "worktree"
    git(root, "worktree", "add", "-b", "other", str(worktree))
    second = tmp_path / "second" / "app"
    second.mkdir(parents=True)
    git(second, "init")
    args = SimpleNamespace(
        kind="repository",
        cwd=root,
        name="app",
        description="",
        project=[],
        path=None,
        actor="process:test",
    )
    first = register(store, args)
    assert first["path"].startswith("/repositories/")
    args.cwd = second
    other = register(store, args)
    assert first["path"] != other["path"]
    idx = Index(store)
    idx.refresh()
    assert current_repository(idx, worktree)[0] == first["path"]
    assert current_repository(idx, second)[0] == other["path"]
    idx.close()


def test_register_reuses_legacy_repository_path(store, tmp_path):
    root = tmp_path / "legacy"
    root.mkdir()
    git(root, "init")
    (root / "source.txt").write_text("source\n")
    git(root, "add", "source.txt")
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
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
    legacy = "/repositorys/legacy-repository.md"
    store.create(
        {"type": "Repository", "title": "Legacy repository"},
        "",
        "process:test",
        "Keep its stable path.",
        legacy,
    )
    (store.cache / "config.json").write_text(
        json.dumps({"repositories": {legacy: repo_identity(root)}})
    )
    result = register(
        store,
        SimpleNamespace(
            kind="repository",
            cwd=root,
            name="Legacy repository",
            description="",
            project=[],
            path=None,
            actor="process:test",
        ),
    )
    assert result["path"] == legacy
    assert result["existing"] is True
