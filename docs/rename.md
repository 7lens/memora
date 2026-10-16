# Memora name and compatibility

The project name is Memora. Install the `memora` Python package from this repository. The command
is `memora`. The Python module is also `memora`. Use `MEMORA_ROOT` to select the memory root.
The public repository is [7lens/memora](https://github.com/7lens/memora).

```sh
.venv/bin/pip install --no-deps .
.venv/bin/memora version
.venv/bin/memora install --dry-run
.venv/bin/memora install
```

## Existing installations

Use the previous installation's uninstall command before you remove its package. This removes
its managed editor instructions and retains unrelated user text. Install Memora in the same
environment, then run `memora install`. Start a new editor session.

Memora keeps the `knowledge/` directory, the `.brain/` local state directory, and the `brain`
frontmatter namespace. These names are data contracts. Existing note identities, event history,
sources, workspace assignments, and remote synchronization state retain their meaning.

The version reader accepts the previous version marker. The next memory write copies its history
to `.memora-version.json`. The old marker remains available for recovery. New private bundles use
`memora-private-v1`; the reader also accepts the previous private bundle format.

This rename needs no memory reconsolidation. The 1.x compatibility rules still apply.

## Study records

The October 2026 study measured the software before this rename. Its raw prompts, responses,
checksums, condition labels, source URNs, model settings, and measurements remain unchanged.
The raw files contain the former project name and module paths as historical data.

Current documentation uses Memora. The condition identifier `brain` still names the same measured
condition. The renamed study runner keeps that identifier and the fixture source URNs to support
comparison. A source hash from the old run identifies the old source, not this renamed checkout.
The recorded measurements remain the same; the rename is not a new model experiment.

## Git identity

The initial Memora commit uses `Devidfirz <Devidfirz@7lens.io>` for its author and committer.
The repository belongs to the `7lens` organization.
