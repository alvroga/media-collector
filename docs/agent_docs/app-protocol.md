# Engine ↔ app protocol (`media_collector serve`) — protocol version 1

Status: **implemented** (`src/media_collector/server.py`, tested in `tests/test_server.py`). ADR-0006.

The SwiftUI app launches `python -m media_collector serve` as a child process and exchanges **one JSON object per line** on stdin/stdout (UTF-8). stderr is for logs only. Any change to fields below must bump `PROTOCOL` and be mirrored in the Swift side.

## Framing
- Request: `{"id": <int>, "cmd": "<name>", ...args}`
- Reply (exactly one per request with an id): `{"id": n, "ok": true, "result": {...}}` or `{"id": n, "ok": false, "error": "<Type>: <message>"}`
- Events (no reply expected): `{"event": "<name>", ...}`. On start the server sends `{"event":"ready","protocol":1,"version":"x.y.z"}`. A malformed request line yields `{"event":"error","message":...}`.
- Closing stdin (or `quit`) cancels any running job and exits.

## Concurrency
`open_project`, `plan` and `run` are **long commands** run on a background thread; only one at a time (a second gets error `busy`). `cancel` and `volumes` are answered immediately even while a job runs. Events from `run` may interleave with the reply to other requests.

## Options object (`plan`, `run`)
Unknown keys are an error (catches drift). All optional:
| key | meaning |
|---|---|
| `include_unused` (bool, false) | also copy media no sequence uses |
| `include_proxies` (bool, false) | also copy proxies of selected originals |
| `sequences` (list of ids \| null) | only media used by these sequences; null = all |
| `keep_from_level` (int ≥ 0 \| null, **0**) | drop the first N folder levels of each source path, keep the rest; **explicit `null` = flatten**; key absent = 0 |
| `project_folder` (string \| null) | put everything under this subfolder |

`mappings`: `{"O:": "/Volumes/Media", "//nas/share": "/Volumes/share"}` — Windows drive/share → local folder (case-insensitive keys). Cache files are never copied.

## Commands
- **`open_project {path}`** → `{path, format, sequences:[{id,name,originals}], files, originals, proxies, unused, cache, non_file_skipped, warnings:[string], can_relink, unmapped_prefixes:[{prefix,files}]}`. Counts exclude cache. `sequences` may be empty (formats without sequences, e.g. After Effects: the app hides its Scope choice); `can_relink` is false for formats that can be read but not relinked (the app disables the relink option). `unmapped_prefixes` lists Windows drives/shares that need a mapping (drives the mapping sheet).
- **`plan {options?, mappings?}`** → `{files, originals, proxies, bytes, missing:{count,items:[{path,reason}]}, unmapped_prefixes, cache_skipped, renamed_on_collision, examples:[{source,dest_rel}]}`. `reason` is `unmapped` or `not_found`. `examples` (≤5, spread across the plan) feed the live path preview. Cheap to call repeatedly (file sizes are cached per session).
- **`run {dest, options?, mappings?, workers?=1, relink?=false, dry_run?=false}`** → events while running, then reply `{ok, cancelled, counts:{status:n}, bytes, problems:[{status,path,detail}], project_copy, relinked_project, relink}`.
  - Events: `progress {id, file_index, file_count, name, phase, file_bytes_done, file_bytes_total, bytes_done, bytes_total}` (≤10/s; overall bar = bytes_done/bytes_total, both passes counted; `phase`: copying|verifying|checking|done) and `file {id, status, source, dest, detail}` per finished file (status: copied, skipped_identical, conflict, missing, failed, cancelled, would_copy).
  - `relink` (when requested): skipped if the copy had any problem (`{"skipped": reason}`), else `{relinked, media_objects, left_unchanged, missing_after}`; `{"error": ...}` if the output project already exists (never overwritten). `relinked_project` is `<name>_relinked.<ext>` in the same folder as the copied original. That folder is where the project's own source folder lands under the media layout rule (`keep_from_level`, `project_folder`): with the project at `/A/B/Show.prproj` and `keep_from_level` 1, it goes to `<dest>/B/`; above the cut, or when flattening, the destination root (or the project folder). `project_copy` `{status,path,detail}` (absent on dry runs and cancels) is the verified copy of the original project into the same folder (`copied`, `conflict`, `failed`); it is made whether or not relinking is requested. Original and relinked project share a version number and nothing is overwritten: `Name.ext` + `Name_relinked.ext`, or if either exists `Name_1.ext` + `Name_1_relinked.ext`, then `_2`, ... (`detail` says so).
- **`cancel`** → `{cancelling: bool}`; the running job stops between chunks, removes its partial file, and the `run` reply has `cancelled: true`.
- **`volumes`** → `{volumes:[{name,path}]}` from `/Volumes` (for mapping pickers).
- **`quit`** → `{}` then exit.
