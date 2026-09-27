# Architecture

Status: implemented (verified against the code on 2026-09-24). Decisions behind it: `docs/adr/`.

Media Collector reads an edit project, finds the media its timelines use, copies that media to a
destination **keeping the folder structure** (skipping the first N levels), and optionally writes a
relinked copy of the project pointing at the copies.

```
 SwiftUI app (app/)  ──JSON lines over stdio──▶  engine (src/media_collector)
   knows nothing about                             readers ─▶ model ─▶ plan ─▶ copier
   formats or copying                                                    └──▶ writers (relink)
```

## Two processes (ADR-0006)

- **App** (`app/Sources/MediaCollector`): SwiftUI, macOS 14+. `EngineClient` launches
  `python -m media_collector serve` (the bundled runtime in `Contents/Resources/engine` when packaged,
  the repo's `.venv` in dev) and speaks the protocol in `app-protocol.md`. `AppModel` holds UI state;
  option changes trigger a debounced `plan` call, so the summary is always live. Engine stderr goes
  to `~/Library/Logs/Media Collector/engine.log`.
- **Engine** (`src/media_collector`): UI-free Python. `server.py` runs one long command at a time
  (`open_project`, `plan`, `run`) on a background thread so `cancel` stays responsive; `volumes`,
  `cancel` and `quit` answer immediately. EOF on stdin cancels the running job and exits.
- The CLI (`cli.py`, `python -m media_collector inspect|copy`) is a dev/test harness over the same
  engine functions. It is where the developer-only `--flatten` flag lives.

## Engine modules

| Module | Role |
|---|---|
| `model.py` | The format-agnostic model: `Project` → `Sequence`s and `MediaRef`s (path string + `PathStyle`, role original/proxy, `used_in` sequence ids, `paired_paths`, `is_cache`). The only interface between readers and everything else. |
| `paths.py` | Path handling: boot-volume alias normalisation (`/Volumes/Macintosh HD/x`, `/System/Volumes/Data/x` → `/x`), `resolve_source` (project path → local `Path` via user mappings for Windows drives/shares or another Mac's folders), `path_from_reference` (plain paths and `file://` URLs from exchange files). |
| `readers/` | One reader per format, dispatched by `read_project` on extension (and root element for `.xml`). Emit a `Project`; never import the planner or copier. |
| `plan.py` | Pure logic, no filesystem. `select` picks media (used only by default; optional unused, proxies with their originals, chosen sequences; never cache). `build_plan` computes each destination path and renames case-insensitive collisions `_2`, `_3`. |
| `copier.py` | Executes a `Plan`. Never imports a reader. |
| `fsutil.py` | The one macOS-specific filesystem call: exclusive, atomic move-into-place. |
| `writers/` | `relink_project` dispatches on format and writes a **new** project file with paths remapped through `Report.path_map()`. |
| `server.py` / `cli.py` | The two front doors. |

Dependency rule (CLAUDE.md boundary, currently true in the code): readers and writers depend on
`model`/`paths`; `plan` depends on `model`; `copier` on `model`, `paths`, `plan`. Adding a format
means adding a reader (and optionally a writer), nothing else.

## Formats

| Format | Reader | Relink writer | Notes |
|---|---|---|---|
| Premiere `.prproj` | yes | yes | Gzipped XML, stream-parsed (projects reach ~1 GB); usage = everything reachable from a `Sequence` through object refs; proxies from `ProxyMedia`. Writer streams line by line and rewrites only path fields. `docs/agent_docs/prproj-format.md` |
| FCP7 XML (xmeml) | yes | yes | No proxy info. |
| FCPXML / `.fcpxmld` | yes | yes | Writer drops stale `<bookmark>`s on relinked entries. |
| OTIO | yes | yes | Proxy detection is a key-name heuristic. |
| AAF | yes (pyaaf2) | yes | Locators only; embedded/Avid-MXF essence is warned about. Writer untested in editing apps. |
| After Effects `.aep` | yes | no | Every footage item counts as used; no sequences. `aep-format.md` |
| EDL, Resolve `.drp`/`.drt`, `.fcpbundle`, `.aepx` | no | no | `read_project` raises with a message telling the user what to export instead. |

`RELINKABLE_FORMATS` (in `writers/__init__.py`) drives `can_relink` in the protocol; the app locks
the relink switch off for anything else.

## Layout rules (ADR-0003)

The destination path is the source path's folder chain minus the first `keep_from_level` components,
plus the file name, optionally under a `project_folder`. Windows drive letters and UNC
server/share count as folder levels. `.` and `..` components are resolved out of both the source
path and the project folder, so nothing can land outside the destination. `keep_from_level: null`
flattens (developer CLI only; the app never sends it).

## Copy semantics (ADR-0005)

Whole files only. For each planned file: stream source → `<name>.mc-partial` while hashing, fsync,
re-read and verify SHA-256, copy timestamps, then move into place with an exclusive rename (`fsutil.move_no_clobber`). Statuses: `copied`, `skipped_identical` (same size and SHA-256), `conflict` (something
different is there; left untouched), `missing`, `failed`, `cancelled`, `would_copy` (dry run).
Cancellation removes the current partial. Progress counts both passes (copy + verify) so one bar
runs 0–100%. Sources are only read.

`move_no_clobber` uses macOS `renamex_np(RENAME_EXCL)`, which is atomic and never replaces a file
(APFS, HFS+). On filesystems without it (exFAT, SMB) it falls back to a check followed by
`os.replace`, leaving a very small race window. The relink writers use the same call for their output.

## Relink

Runs only after a fully clean copy (`Report.ok`). A failed relink removes its partial file (and a half-built `.fcpxmld` bundle) so a retry is never blocked; a failed re-read of the finished output is reported as a note and the file is kept. Both the original project (verified copy, same rules as media) and the relinked one go in the folder the project's own source folder maps to under the media layout rule (`plan.project_folder_parts`; the destination root when that folder is above the skipped levels), the latter as `<name>_relinked.<ext>`. Nothing is overwritten: they share a version number, `Name.ext` + `Name_relinked.ext`, or `Name_1.ext` + `Name_1_relinked.ext` (then `_2`, ...) if either exists (`fsutil.next_version`); the source is never touched. Writers keep each reference's original
style (`file://` URL, absolute, or relative) via `format_like`, then re-read the output with the
normal reader and report any relinked path that does not exist (`missing_after`).

## Tests

`tests/` (pytest) covers each layer; some tests use real sample projects kept outside the repo (they skip themselves when absent), and the Swift tests in `app/Tests` start the real engine. The Python tests, `ruff check src
tests` and `swift test` are the pre-commit bar; commands in `how-to-run.md`.

## Known limitations

The open issues are the live list; the structural ones are: no proxy discovery beyond what the project
records, `.aep` cannot be relinked and has no per-composition usage, AAF relink is unverified in
editing apps, and only Apple-silicon macOS packaging exists.
