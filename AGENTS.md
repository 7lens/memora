# Memora

Use ASD-STE100, Issue 9, for new documentation, memory notes, and interface text. Keep code and source quotations unchanged.

Read `START.md` before work. After a pull of `main`, update the local CLI and check memory compatibility before you load context. Use Markdown as the source of truth. Keep the search index disposable.

Use Python 3.11 or later. Run `.venv/bin/pytest` after a behavior change. Run the browser test after a viewer change.

Keep unknown frontmatter fields. Preserve immutable events. Use revision checks and managed transactions for note changes.

Do not claim that automatic language checks certify STE compliance. Record the scope of each check.

Store personal memory in `knowledge/`, which Git ignores on every branch. The CLI checks this rule before each write. Do not force-add, commit, or push memory data.
