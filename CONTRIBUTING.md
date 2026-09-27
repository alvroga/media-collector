# Contributing

Thanks for helping. A few things that keep the project healthy:

## Set up
```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest           # engine tests
.venv/bin/ruff check src tests       # lint
cd app && swift test                 # app tests (they start the engine from ../.venv)
```
macOS 14+ and the Xcode command line tools are required. Details: [docs/agent_docs/how-to-run.md](docs/agent_docs/how-to-run.md).

## Sample projects
Tests that need real editing projects (large, and they can contain client paths) skip themselves when the
files are not present, so the suite passes on a clean checkout. Never commit sample projects; `assets/` is
git-ignored for exactly that reason. Small synthetic fixtures built inside the tests are welcome.

## Ground rules
The rules in [CLAUDE.md](CLAUDE.md) apply to everyone, not only AI assistants. The important ones:
- Never modify source media or the source project; copy-only, whole files, verified.
- Never overwrite a file at the destination silently.
- Always keep the folder structure.
- Format readers and the copy engine share only the media-reference model in `model.py`; adding a format means
  adding a reader (and optionally a writer), nothing else.

## Changes
- A real architecture choice gets an ADR in `docs/adr/` first.
- A user-visible change adds a line under `[Unreleased]` in `CHANGELOG.md` in the same pull request.
- Include tests, and run the three commands above before opening the pull request.
- Bug reports: say the app version, the project format, and (without sharing private media) what the report
  screen or the engine log shows. The engine log is `~/Library/Logs/Media Collector/engine.log`.
