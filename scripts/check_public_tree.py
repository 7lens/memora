"""Reject knowledge data in a public release tree."""

from pathlib import Path
import subprocess
import sys


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        ["git", "ls-files", "--cached", "knowledge", "obsidian"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    tracked = sorted(result.stdout.splitlines())
    if tracked:
        print("Do not track local memory data: " + ", ".join(tracked))
        return 1
    print("The public tree does not track local memory data.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
