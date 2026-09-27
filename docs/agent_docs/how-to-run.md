# How to run Media Collector

macOS only (ADR-0004). Python 3.11+ for the engine, Xcode command line tools for the app.

## Set up the engine (once)

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

The virtualenv holds absolute paths: recreate it (and `rm -rf app/.build`) after moving or renaming the folder.

## Developer CLI (a test harness, not a deliverable)

```bash
.venv/bin/python -m media_collector inspect PROJECT
.venv/bin/python -m media_collector copy PROJECT DEST [--dry-run] [--include-proxies] [--relink]
```

## App

```bash
cd app && swift run MediaCollector      # dev build; starts the engine from ../.venv
app/scripts/build_app.sh                # self-contained .app, .zip and .dmg in app/build/
```

Environment overrides: `MEDIA_COLLECTOR_REPO` (repo root), `MEDIA_COLLECTOR_PYTHON` (interpreter),
`MEDIA_COLLECTOR_SNAPSHOT_DIR` (renders UI snapshot tests into that folder).

## Tests and lint

```bash
.venv/bin/python -m pytest              # some tests use fixtures in ~/Documents (sample projects; skipped when absent)
.venv/bin/ruff check src tests
cd app && swift test
```

Release steps: `docs/release_process.md`. Engine protocol: `docs/agent_docs/app-protocol.md`.
