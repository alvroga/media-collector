"""Developer/test harness around the engine — not a deliverable (ADR-0006).

python -m media_collector inspect PROJECT
python -m media_collector copy PROJECT DEST [--dry-run] [--include-unused] [--include-proxies] ...
"""

from __future__ import annotations

import argparse
import signal
import sys
import threading
from pathlib import Path

from media_collector.copier import Status, execute
from media_collector.model import Project
from media_collector.plan import PlanOptions, build_plan
from media_collector.readers import read_project


def _map_arg(text: str) -> tuple[str, str]:
    prefix, sep, folder = text.partition("=")
    if not sep or not prefix or not folder:
        raise argparse.ArgumentTypeError(f"{text!r}: expected PREFIX=FOLDER, e.g. O:=/Volumes/X")
    return prefix, folder


def _non_negative(text: str) -> int:
    try:
        n = int(text)
    except ValueError:
        n = -1
    if n < 0:
        raise argparse.ArgumentTypeError(f"{text!r}: expected a whole number >= 0")
    return n


def _sequence_ids(project: Project, wanted: list[str]) -> tuple[str, ...]:
    ids = []
    for w in wanted:
        by_id = [s for s in project.sequences if s.id == w or s.id.startswith(w) and len(w) >= 6]
        by_name = [s for s in project.sequences if s.name == w]
        hits = by_id or by_name
        if len(hits) != 1:
            kind = "matches nothing" if not hits else f"is ambiguous ({len(hits)} sequences)"
            sys.exit(f"--sequence {w!r} {kind}; use an id from `inspect`")
        ids.append(hits[0].id)
    return tuple(ids)


def cmd_inspect(args: argparse.Namespace) -> int:
    p = read_project(args.project)
    print(
        f"{p.format} project: {len(p.sequences)} sequences, {len(p.media)} files "
        f"({len(p.originals())} originals, {len(p.proxies())} proxies), "
        f"{sum(m.is_cache for m in p.media)} cache, {p.skipped_non_file_media} non-file skipped"
    )
    for s in p.sequences:
        n = sum(
            1
            for m in p.media
            if s.id in m.used_in and not m.is_cache and m.role.value == "original"
        )
        print(f"  seq {s.id[:8]}  {n:4d} originals  {s.name}")
    if args.media:
        for m in p.media:
            tag = "cache" if m.is_cache else m.role.value
            print(f"  {tag:8} {'used' if m.used_in else 'unused':6} {m.path}")
    return 0


def cmd_copy(args: argparse.Namespace) -> int:
    p = read_project(args.project)
    opts = PlanOptions(
        include_unused=args.include_unused,
        include_proxies=args.include_proxies,
        sequences=_sequence_ids(p, args.sequence) if args.sequence else None,
        preserve_after_levels=None if args.flatten else args.keep_from_level,
        project_subfolder=args.project_folder,
    )
    mappings = dict(args.map)
    plan = build_plan(p, opts)
    print(
        f"plan: {len(plan.copies)} files, {plan.skipped_cache} cache skipped, "
        f"{plan.renamed_on_collision} renamed on collision"
    )

    def show(r):
        print(f"  {r.status.value:17} {r.dest.name}" + (f"  ({r.detail})" if r.detail else ""))

    cancel = threading.Event()
    # Ctrl-C asks the copy to stop cleanly (partial files removed) instead of unwinding mid-copy.
    signal.signal(signal.SIGINT, lambda *_: cancel.set())
    try:
        rep = execute(
            plan,
            Path(args.dest),
            dry_run=args.dry_run,
            mappings=mappings,
            progress=show if args.verbose else None,
            cancel=cancel,
            workers=args.workers,
        )
    except KeyboardInterrupt:
        cancel.set()
        print("cancelled")
        return 130
    if rep.cancelled:
        print("cancelled")
        return 130
    parts = [f"{s.value}={rep.count(s)}" for s in Status if rep.count(s)]
    print(f"{'DRY RUN ' if args.dry_run else ''}{', '.join(parts)}  {rep.total_bytes / 1e6:.1f} MB")
    for r in rep.results:
        if r.status in (Status.CONFLICT, Status.MISSING, Status.FAILED):
            print(f"  ! {r.status.value}: {r.media.path} — {r.detail}")
    if args.relink and not args.dry_run:
        if not rep.ok:
            print("not relinking: the copy had conflicts, missing or failed files")
            return 1
        return _relink(args, rep)
    return 0 if rep.ok else 1


def _relink(args: argparse.Namespace, rep) -> int:
    from media_collector.copier import copy_project_file
    from media_collector.fsutil import next_version, numbered_name
    from media_collector.writers import relink_project, relinked_name

    src, dest = Path(args.project), Path(args.dest)
    v = next_version(dest, src.name, relinked_name)
    pc = copy_project_file(src, dest, numbered_name(src.name, v))
    print(f"original project: {pc.status.value}: {pc.dest}")
    out = dest / relinked_name(numbered_name(src.name, v))
    try:
        res = relink_project(src, out, rep.path_map())
    except (ValueError, FileExistsError) as e:
        print(f"relink failed: {e}")
        return 1
    print(f"relinked project: {out}")
    print(
        f"  {res.relinked} of {res.media_objects} media references relinked; "
        f"{len(res.left_unchanged)} left pointing at their original location"
    )
    for note in res.notes:
        print(f"  note: {note}")
    for p in res.missing_after:
        print(f"  ! after relink, not found on disk: {p}")
    return 0 if not res.missing_after else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="media-collector", description="Media Collector (dev harness)"
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    i = sub.add_parser("inspect", help="summarise a project")
    i.add_argument("project")
    i.add_argument("--media", action="store_true", help="list every file")
    i.set_defaults(fn=cmd_inspect)

    c = sub.add_parser("copy", help="copy a project's media")
    c.add_argument("project")
    c.add_argument("dest")
    c.add_argument("--dry-run", action="store_true")
    c.add_argument("--include-unused", action="store_true", help="also copy media no sequence uses")
    c.add_argument("--include-proxies", action="store_true")
    c.add_argument(
        "--sequence",
        action="append",
        default=[],
        metavar="ID_OR_NAME",
        help="only media used by this sequence (repeatable)",
    )
    c.add_argument(
        "--keep-from-level",
        type=_non_negative,
        default=0,
        metavar="N",
        help="drop the first N folder levels of each source path, keep the rest",
    )
    c.add_argument("--flatten", action="store_true", help="no folders (collisions get _2 suffix)")
    c.add_argument("--project-folder", metavar="NAME", help="put everything in this subfolder")
    c.add_argument(
        "--map",
        action="append",
        default=[],
        type=_map_arg,
        metavar="O:=/Volumes/X",
        help="map a Windows drive/share to a local folder (repeatable)",
    )
    c.add_argument(
        "--workers",
        type=int,
        default=1,
        metavar="N",
        help="parallel file copies (can help on network shares; default 1)",
    )
    c.add_argument(
        "--relink",
        action="store_true",
        help="write a relinked copy of the project into DEST (after a clean copy)",
    )
    c.add_argument("-v", "--verbose", action="store_true")
    c.set_defaults(fn=cmd_copy)

    sv = sub.add_parser("serve", help="JSON-lines engine server on stdin/stdout (used by the app)")
    sv.set_defaults(fn=lambda _a: __import__("media_collector.server", fromlist=["main"]).main())

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
