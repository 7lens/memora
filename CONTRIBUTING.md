# Contribute

Keep the public memory empty. Use temporary test data for examples. Do not add personal notes, local paths, credentials, or source artifacts.

Use Python 3.11 or later. Install the test tools with `pip install '.[test]'`. Run these checks before a pull request:

```sh
python scripts/check_public_tree.py
ruff check src tests scripts
ruff format --check src tests scripts
pytest
python scripts/browser_test.py
```

The browser test needs Node.js 22 or later and Chrome. Use `--chrome <path>` to select Chrome.

Add tests for a behavior change. Keep Markdown as the source of truth. Preserve unknown OKF fields and note history.

Use ASD-STE100 Issue 9 for new prose. Keep code, product names, and source quotations unchanged. The license contains unchanged legal text.

Reinstall the package after a code change with `pip install . --no-deps --force-reinstall`. Run `memora language check` on each changed document.

Describe the problem, the change, and the test results in the pull request. State any test that you could not run.
