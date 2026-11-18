#!/bin/sh
# Builds dist/pathfinder_engine-<version>-py3-none-any.whl for the browser (micropip) and for any plain pip install.
# Uses `python -m build` when it is installed, else `pip wheel`; both read pyproject.toml and include data/*.json.
set -e
cd "$(dirname "$0")"
rm -rf dist build
if python3 -c "import build" 2>/dev/null; then
    python3 -m build --wheel --outdir dist
else
    pip wheel . --no-deps --no-build-isolation -w dist 2>/dev/null || pip wheel . --no-deps -w dist
fi
ls -1 dist/*.whl
