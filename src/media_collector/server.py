"""`media_collector serve`: the engine as a JSON-lines server on stdin/stdout (ADR-0006).

One JSON object per line in each direction. Protocol: docs/agent_docs/app-protocol.md.
Requests  {"id": <int>, "cmd": "<name>", ...args}
Replies   {"id": <int>, "ok": true, "result": {...}} | {"id": <int>, "ok": false, "error": "..."}
Events    {"event": "<name>", ...}   (ready, progress, file)
Long commands (open_project, plan, run) run on a background thread so `cancel` stays responsive;
only one may run at a time.
"""

from __future__ import annotations

import dataclasses
import json
import sys
import threading
import time
from pathlib import Path
from typing import Any, TextIO

from media_collector import __version__
from media_collector.copier import Status, copy_project_file, execute
from media_collector.fsutil import next_version, numbered_name
from media_collector.model import MediaRef, Project
from media_collector.paths import foreign_prefix, resolve_source
from media_collector.plan import Plan, PlanOptions, build_plan, project_folder_parts
from media_collector.readers import normalize_project_path, read_project
from media_collector.writers import RELINKABLE_FORMATS, relink_project, relinked_name

PROTOCOL = 1
_OPTION_KEYS = {
    "include_unused",
    "include_proxies",
    "sequences",
    "keep_from_level",
    "project_folder",
}
_LIST_LIMIT = 50


class ProtocolError(Exception):
    pass


def parse_options(d: dict[str, Any] | None) -> PlanOptions:
    d = d or {}
    extra = set(d) - _OPTION_KEYS
    if extra:
        raise ProtocolError(f"unknown option(s): {', '.join(sorted(extra))}")
    seqs = d.get("sequences")
    if seqs is not None and not (isinstance(seqs, list) and all(isinstance(s, str) for s in seqs)):
        raise ProtocolError("sequences must be a list of sequence ids or null")
    level = d.get("keep_from_level", 0)  # missing = 0; explicit null = flatten
    if level is not None and (not isinstance(level, int) or isinstance(level, bool) or level < 0):
        raise ProtocolError("keep_from_level must be a non-negative integer or null")
    return PlanOptions(
        include_unused=bool(d.get("include_unused", False)),
        include_proxies=bool(d.get("include_proxies", False)),
        sequences=tuple(seqs) if seqs is not None else None,
        preserve_after_levels=level,
        project_subfolder=d.get("project_folder") or None,
    )


class Server:
    def __init__(self, stdin: TextIO, stdout: TextIO):
        self.stdin, self.stdout = stdin, stdout
        self._out_lock = threading.Lock()
        self._job: threading.Thread | None = None
        self._cancel = threading.Event()
        self.project: Project | None = None
        self.project_path: Path | None = None
        self._sizes: dict[tuple, int | None] = {}
        self._gone = False

    # ---- output -------------------------------------------------------------------------
    def send(self, msg: dict[str, Any]) -> None:
        if self._gone:
            return
        line = json.dumps(msg, default=_json_default, ensure_ascii=False)
        try:
            with self._out_lock:
                self.stdout.write(line + "\n")
                self.stdout.flush()
        except (BrokenPipeError, ValueError, OSError):
            # The app went away (pipe closed): stop the running job and wind down quietly.
            self._gone = True
            self._cancel.set()

    def reply(self, rid, result=None, error: str | None = None) -> None:
        if error is not None:
            self.send({"id": rid, "ok": False, "error": error})
        else:
            self.send({"id": rid, "ok": True, "result": result})

    # ---- main loop ----------------------------------------------------------------------
    def serve(self) -> int:
        self.send({"event": "ready", "protocol": PROTOCOL, "version": __version__})
        for line in self.stdin:
            if self._gone:
                break
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
                if not isinstance(req, dict) or "cmd" not in req:
                    raise ProtocolError("request must be an object with a 'cmd'")
            except (json.JSONDecodeError, ProtocolError) as e:
                self.send({"event": "error", "message": f"bad request: {e}"})
                continue
            rid = req.get("id")
            try:
                self._dispatch(rid, req)
            except (ProtocolError, ValueError, KeyError, TypeError, OSError) as e:
                self.reply(rid, error=f"{type(e).__name__}: {e}")
            if req["cmd"] == "quit":
                break
        self._cancel.set()  # EOF / quit: stop any running job cleanly
        if self._job:
            self._job.join()
        return 0

    def _dispatch(self, rid, req: dict[str, Any]) -> None:
        cmd = req["cmd"]
        if cmd == "quit":
            self.reply(rid, {})
        elif cmd == "cancel":
            busy = bool(self._job and self._job.is_alive())
            self._cancel.set()
            self.reply(rid, {"cancelling": busy})
        elif cmd == "volumes":
            self.reply(rid, {"volumes": _volumes()})
        elif cmd in ("open_project", "plan", "run"):
            self._start_job(rid, cmd, req)
        else:
            raise ProtocolError(f"unknown command {cmd!r}")

    def _start_job(self, rid, cmd: str, req: dict[str, Any]) -> None:
        if self._job and self._job.is_alive():
            raise ProtocolError("busy: another command is still running")
        self._cancel = threading.Event()
        fn = {"open_project": self._open_project, "plan": self._plan, "run": self._run}[cmd]

        def work() -> None:
            try:
                self.reply(rid, fn(rid, req))
            except Exception as e:  # noqa: BLE001 - every failure must reach the client
                self.reply(rid, error=f"{type(e).__name__}: {e}")

        self._job = threading.Thread(target=work, name=f"mc-{cmd}")
        self._job.start()

    # ---- commands -----------------------------------------------------------------------
    def _require_project(self) -> Project:
        if self.project is None:
            raise ProtocolError("no project open; send open_project first")
        return self.project

    def _open_project(self, rid, req) -> dict[str, Any]:
        path = normalize_project_path(Path(req["path"]).expanduser())
        if not path.exists():
            raise ProtocolError(f"not found: {path}")
        # read_project explains unsupported types (Final Cut libraries, Resolve projects, ...)
        self.project, self.project_path = read_project(path), path
        self._sizes.clear()
        p = self.project
        per_seq = {s.id: 0 for s in p.sequences}
        for m in p.media:
            if m.role.value == "original" and not m.is_cache:
                for sid in m.used_in:
                    if (
                        sid in per_seq
                    ):  # formats without real sequences use a synthetic "everything" id
                        per_seq[sid] += 1
        return {
            "path": str(path),
            "format": p.format,
            "sequences": [
                {"id": s.id, "name": s.name, "originals": per_seq[s.id]} for s in p.sequences
            ],
            "files": len([m for m in p.media if not m.is_cache]),
            "originals": len([m for m in p.originals() if not m.is_cache]),
            "proxies": len([m for m in p.proxies() if not m.is_cache]),
            "unused": len([m for m in p.media if not m.used_in and not m.is_cache]),
            "cache": sum(m.is_cache for m in p.media),
            "non_file_skipped": p.skipped_non_file_media,
            "warnings": p.warnings,
            "can_relink": p.format in RELINKABLE_FORMATS,
            "unmapped_prefixes": _unmapped(p.media, {}),
        }

    def _size(self, m: MediaRef, mappings: dict[str, str]) -> tuple[int | None, str | None]:
        src = resolve_source(m, mappings)
        if src is None:
            return None, "unmapped"
        key = (str(src),)
        if key not in self._sizes:
            try:
                self._sizes[key] = src.stat().st_size if src.is_file() else None
            except OSError:
                self._sizes[key] = None
        size = self._sizes[key]
        return size, (None if size is not None else "not_found")

    def _plan(self, rid, req) -> dict[str, Any]:
        p = self._require_project()
        mappings = dict(req.get("mappings") or {})
        plan = build_plan(p, parse_options(req.get("options")))
        total, missing = 0, []
        for c in plan.copies:
            size, problem = self._size(c.source, mappings)
            if problem:
                missing.append({"path": c.source.path, "reason": problem})
            else:
                total += size or 0
            if self._cancel.is_set():
                raise ProtocolError("cancelled")
        n = len(plan.copies)
        step = max(1, n // 5)
        return {
            "files": n,
            "originals": sum(c.source.role.value == "original" for c in plan.copies),
            "proxies": sum(c.source.role.value == "proxy" for c in plan.copies),
            "bytes": total,
            "missing": {"count": len(missing), "items": missing[:_LIST_LIMIT]},
            "unmapped_prefixes": _unmapped([c.source for c in plan.copies], mappings),
            "cache_skipped": plan.skipped_cache,
            "unusable": len(plan.unusable),
            "renamed_on_collision": plan.renamed_on_collision,
            "examples": [
                {"source": c.source.path, "dest_rel": c.dest_rel} for c in plan.copies[::step][:5]
            ],
        }

    def _run(self, rid, req) -> dict[str, Any]:
        p = self._require_project()
        dest = Path(req["dest"]).expanduser()
        mappings = dict(req.get("mappings") or {})
        opts = parse_options(req.get("options"))
        plan: Plan = build_plan(p, opts)
        workers = int(req.get("workers", 1))
        last = [0.0]

        def on_progress(pr) -> None:
            now = time.monotonic()
            if now - last[0] >= 0.1 or pr.bytes_done >= pr.bytes_total:
                last[0] = now
                self.send({"event": "progress", "id": rid, **dataclasses.asdict(pr)})

        def on_file(r) -> None:
            self.send(
                {
                    "event": "file",
                    "id": rid,
                    "status": r.status.value,
                    "source": r.source and str(r.source),
                    "dest": str(r.dest),
                    "detail": r.detail,
                }
            )

        rep = execute(
            plan,
            dest,
            dry_run=bool(req.get("dry_run", False)),
            mappings=mappings,
            progress=on_file,
            on_progress=on_progress,
            cancel=self._cancel,
            workers=workers,
        )
        result: dict[str, Any] = {
            "ok": rep.ok,
            "cancelled": rep.cancelled,
            "counts": {s.value: rep.count(s) for s in Status if rep.count(s)},
            "bytes": rep.total_bytes,
            "problems": [
                {"status": r.status.value, "path": r.media.path, "detail": r.detail}
                for r in rep.results
                if r.status in (Status.CONFLICT, Status.MISSING, Status.FAILED, Status.CANCELLED)
            ][:_LIST_LIMIT],
            "project_copy": None,
            "relinked_project": None,
            "relink": None,
        }
        # The project itself goes with the media, in the folder its own source folder maps to (same layout
        # rule as the media): the original and (below) the relinked one, sharing a version number (`Show.prproj`, or `Show_1.prproj` + `Show_1_relinked.prproj` if those exist).
        target_dir = dest.joinpath(*project_folder_parts(self.project_path, opts))
        name = self.project_path.name
        version = next_version(target_dir, name, relinked_name)
        if not req.get("dry_run") and not rep.cancelled:
            pc = copy_project_file(self.project_path, target_dir, numbered_name(name, version))
            result["project_copy"] = {
                "status": pc.status.value,
                "path": str(pc.dest),
                "detail": pc.detail
                or ("" if version == 0 else "a project with this name was already there"),
            }
        if req.get("relink") and not req.get("dry_run"):
            if not rep.ok:
                result["relink"] = {"skipped": "the copy had problems; fix them and run again"}
            else:
                out = target_dir / relinked_name(numbered_name(name, version))
                try:
                    out.parent.mkdir(parents=True, exist_ok=True)
                    res = relink_project(self.project_path, out, rep.path_map())
                    result["relinked_project"] = str(out)
                    result["relink"] = {
                        "relinked": res.relinked,
                        "media_objects": res.media_objects,
                        "left_unchanged": len(res.left_unchanged),
                        "missing_after": res.missing_after[:_LIST_LIMIT],
                        "notes": res.notes,
                    }
                except (FileExistsError, ValueError, OSError) as e:
                    result["relink"] = {"error": f"{type(e).__name__}: {e}"}
        return result


def _unmapped(refs, mappings: dict[str, str]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for m in refs:
        if m.is_cache:
            continue
        pre = foreign_prefix(m)
        if pre is not None and resolve_source(m, mappings) is None:
            counts[pre] = counts.get(pre, 0) + 1
    return [{"prefix": k, "files": v} for k, v in sorted(counts.items())]


def _volumes() -> list[dict[str, str]]:
    root = Path("/Volumes")
    out = []
    if root.is_dir():
        for e in sorted(root.iterdir()):
            out.append({"name": e.name, "path": str(e.resolve() if e.is_symlink() else e)})
    return out


def _json_default(o: Any) -> Any:
    if isinstance(o, Path):
        return str(o)
    raise TypeError(f"not JSON serialisable: {type(o).__name__}")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    return Server(sys.stdin, sys.stdout).serve()


if __name__ == "__main__":
    raise SystemExit(main())
