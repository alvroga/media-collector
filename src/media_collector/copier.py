"""Executes a `Plan`: whole-file, verified, non-destructive copies (ADR-0005, CLAUDE.md).

- Sources are only ever read. Destination files are written to a `.mc-partial` name and renamed
  into place once their checksum matches the source, so an interrupted run never leaves a
  half-written file under its real name (resume = run again).
- An existing destination file is skipped if identical (same size and SHA-256), otherwise reported
  as a conflict and left untouched. Nothing is ever overwritten.
- GUI-ready: byte-level progress, cooperative cancellation, and optional parallel workers.
  Callbacks run on worker threads — a UI must marshal them onto its own thread.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from media_collector.fsutil import move_no_clobber
from media_collector.model import MediaRef, PathStyle
from media_collector.paths import resolve_source
from media_collector.plan import Plan, PlannedCopy

CHUNK = 8 * 1024 * 1024
# Flush to the destination this often while copying. Network shares buffer writes and only really send
# them at fsync: syncing once at the end hides the transfer inside one call that can neither show
# progress nor be cancelled. Syncing every so often keeps the progress bar honest and bounds how long a
# Cancel can take to about one interval.
SYNC_EVERY = 32 * 1024 * 1024
PARTIAL_SUFFIX = ".mc-partial"


class Status(str, Enum):
    COPIED = "copied"
    SKIPPED_IDENTICAL = "skipped_identical"
    CONFLICT = "conflict"  # different file already at destination; left untouched
    MISSING = "missing"  # source not found / unmapped
    FAILED = "failed"  # I/O error or checksum mismatch
    CANCELLED = "cancelled"  # not (fully) processed because the run was cancelled
    WOULD_COPY = "would_copy"  # dry run


@dataclass
class CopyResult:
    media: MediaRef
    status: Status
    source: Path | None
    dest: Path
    size: int = 0
    sha256: str = ""
    detail: str = ""


@dataclass(frozen=True)
class Progress:
    """Snapshot for a progress UI. Overall counts include both passes (copy + verify) of every
    resolvable file, so one bar runs 0 -> 100%; files that are skipped/conflict/missing/cancelled
    fast-forward their share."""

    file_index: int
    file_count: int
    name: str
    phase: str  # "copying" | "verifying" | "checking" | "done"
    file_bytes_done: int
    file_bytes_total: int
    bytes_done: int
    bytes_total: int


@dataclass
class Report:
    results: list[CopyResult] = field(default_factory=list)

    def count(self, status: Status) -> int:
        return sum(1 for r in self.results if r.status is status)

    @property
    def cancelled(self) -> bool:
        return any(r.status is Status.CANCELLED for r in self.results)

    @property
    def ok(self) -> bool:
        bad = (Status.CONFLICT, Status.MISSING, Status.FAILED, Status.CANCELLED)
        return not any(r.status in bad for r in self.results)

    @property
    def total_bytes(self) -> int:
        return sum(r.size for r in self.results)

    def path_map(self) -> dict[str, Path]:
        """Original project path -> new absolute location, for every file that now exists at
        the destination (copied or already identical). Input for relink writers."""
        good = (Status.COPIED, Status.SKIPPED_IDENTICAL)
        return {r.media.path: r.dest for r in self.results if r.status in good}


class _Cancelled(Exception):
    pass


class _Meter:
    """Thread-safe overall progress accounting."""

    def __init__(self, total: int, count: int, cb: Callable[[Progress], None] | None):
        self._lock = threading.Lock()
        self.total, self.done, self.count, self.cb = total, 0, count, cb

    def advance(self, n: int, item: _Item, phase: str) -> None:
        item.advanced += n
        with self._lock:
            self.done += n
            done = self.done
        if self.cb:
            self.cb(
                Progress(
                    item.index,
                    self.count,
                    item.name,
                    phase,
                    min(item.advanced, item.size),
                    item.size,
                    done,
                    self.total,
                )
            )

    def finish(self, item: _Item) -> None:
        rest = max(0, 2 * item.size - item.advanced)
        self.advance(rest, item, "done")


@dataclass
class _Item:
    index: int
    name: str
    size: int
    advanced: int = 0


def _sha256(
    path: Path, check: Callable[[], None], tick: Callable[[int], None] | None = None
) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(CHUNK):
            check()
            h.update(chunk)
            if tick:
                tick(len(chunk))
    return h.hexdigest()


def execute(
    plan: Plan,
    dest_root: Path,
    *,
    dry_run: bool = False,
    mappings: dict[str, str] | None = None,
    progress: Callable[[CopyResult], None] | None = None,
    on_progress: Callable[[Progress], None] | None = None,
    cancel: threading.Event | None = None,
    workers: int = 1,
) -> Report:
    """Run `plan`. `progress` fires per finished file; `on_progress` fires per chunk.
    Set `cancel` to stop: the current file's partial is removed and the rest are CANCELLED."""
    dest_root = Path(dest_root)
    cancel = cancel or threading.Event()
    jobs = []
    total = 0
    for i, item in enumerate(plan.copies):
        src = resolve_source(item.source, mappings)
        size = src.stat().st_size if src is not None and src.is_file() else 0
        total += 2 * size
        jobs.append(
            (
                _Item(i, item.dest_rel.rsplit("/", 1)[-1], size),
                item.source,
                src,
                dest_root / item.dest_rel,
            )
        )
    meter = _Meter(total, len(jobs), on_progress)

    def run(job) -> CopyResult:
        it, media, src, dest = job
        if cancel.is_set():
            res = CopyResult(
                media, Status.CANCELLED, src, dest, it.size, detail="cancelled before start"
            )
        else:
            res = _one(media, src, dest, dry_run, it, meter, cancel)
        meter.finish(it)
        if progress:
            progress(res)
        return res

    if workers > 1 and len(jobs) > 1:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(run, jobs))
    else:
        results = [run(j) for j in jobs]
    return Report(results=results)


def _one(
    media, src, dest, dry_run, it: _Item, meter: _Meter, cancel: threading.Event
) -> CopyResult:
    if src is None or not src.is_file():
        why = "no path mapping for this drive/share" if src is None else "source file not found"
        return CopyResult(media, Status.MISSING, src, dest, detail=why)

    def check() -> None:
        if cancel.is_set():
            raise _Cancelled

    partial = dest.with_name(dest.name + PARTIAL_SUFFIX)
    size = it.size
    try:
        check()
        if dest.exists():
            if dest.is_file() and dest.stat().st_size == size:
                digest = _sha256(src, check, lambda n: meter.advance(n, it, "checking"))
                if _sha256(dest, check, lambda n: meter.advance(n, it, "checking")) == digest:
                    return CopyResult(media, Status.SKIPPED_IDENTICAL, src, dest, size, digest)
            return CopyResult(
                media,
                Status.CONFLICT,
                src,
                dest,
                size,
                detail="different file already exists at destination",
            )
        if dry_run:
            return CopyResult(media, Status.WOULD_COPY, src, dest, size)
        dest.parent.mkdir(parents=True, exist_ok=True)
        h = hashlib.sha256()
        with open(src, "rb") as fin, open(partial, "wb") as fout:
            unsynced = 0
            while chunk := fin.read(CHUNK):
                check()
                h.update(chunk)
                fout.write(chunk)
                unsynced += len(chunk)
                if unsynced >= SYNC_EVERY:
                    fout.flush()
                    os.fsync(fout.fileno())
                    unsynced = 0
                meter.advance(len(chunk), it, "copying")
            fout.flush()
            os.fsync(fout.fileno())
        digest = h.hexdigest()
        if _sha256(partial, check, lambda n: meter.advance(n, it, "verifying")) != digest:
            partial.unlink(missing_ok=True)
            return CopyResult(
                media, Status.FAILED, src, dest, size, detail="checksum mismatch after copy"
            )
        shutil.copystat(src, partial)
        try:
            move_no_clobber(partial, dest)  # never replaces a file that appeared meanwhile
        except FileExistsError:
            partial.unlink(missing_ok=True)
            return CopyResult(
                media,
                Status.CONFLICT,
                src,
                dest,
                size,
                detail="a file appeared at the destination during the copy",
            )
        return CopyResult(media, Status.COPIED, src, dest, size, digest)
    except _Cancelled:
        partial.unlink(missing_ok=True)
        return CopyResult(media, Status.CANCELLED, src, dest, size, detail="cancelled")
    except OSError as e:
        partial.unlink(missing_ok=True)
        return CopyResult(media, Status.FAILED, src, dest, detail=f"{type(e).__name__}: {e}")


def copy_project_file(src: Path, dest_dir: Path, dest_name: str | None = None) -> CopyResult:
    """Copy the source project itself (a file, or a bundle such as `.fcpxmld`) into `dest_dir` as
    `dest_name` (default: its own name). Verified like media; never overwrites (CONFLICT if the name
    is taken; callers pick a free versioned name with `fsutil.next_version`)."""
    src, dest_dir = Path(src), Path(dest_dir)
    name = dest_name or src.name
    dest = dest_dir / name
    ref = MediaRef(path=str(src), path_style=PathStyle.POSIX)
    if not src.is_dir():
        return execute(Plan([PlannedCopy(ref, name)]), dest_dir).results[0]
    try:
        if dest.exists():
            return CopyResult(ref, Status.CONFLICT, src, dest, detail="already exists there")
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dest)
        return CopyResult(ref, Status.COPIED, src, dest)
    except OSError as e:
        return CopyResult(ref, Status.FAILED, src, dest, detail=f"{type(e).__name__}: {e}")
