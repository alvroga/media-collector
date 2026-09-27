"""Copy planning: which media to copy and where it lands. Pure logic, no filesystem access.

Consumes only `media_collector.model` (never a reader), so it works for every format (CLAUDE.md boundaries).
Layout rules: docs/adr/0003-keep-structure-means-disk-tree.md
"""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass, field
from pathlib import Path

from media_collector.model import MediaRef, PathStyle, Project, Role
from media_collector.paths import canonical_posix


@dataclass
class PlanOptions:
    # Also copy media that no sequence uses (imported but never edited in). Off = used media only.
    include_unused: bool = False
    # Sequence ids to take used media from; None = every sequence. Media used only by other
    # sequences is left out. `include_unused` still adds media that NO sequence uses.
    sequences: tuple[str, ...] | None = None
    include_proxies: bool = False
    # None = flatten (opt-in only, CLAUDE.md). N = drop the first N folder levels of each
    # source path and keep everything below (Resolve's "preserve hierarchy after N levels").
    preserve_after_levels: int | None = 0
    project_subfolder: str | None = None

    def __post_init__(self) -> None:
        if self.preserve_after_levels is not None and self.preserve_after_levels < 0:
            raise ValueError("preserve_after_levels must be >= 0 (or None to flatten)")


@dataclass
class PlannedCopy:
    source: MediaRef
    dest_rel: str  # POSIX-style path relative to the destination root


@dataclass
class Plan:
    copies: list[PlannedCopy] = field(default_factory=list)
    renamed_on_collision: int = 0
    skipped_cache: int = 0
    # Media whose path has no usable file name (e.g. '/'); left out of the plan, never silently.
    unusable: list[str] = field(default_factory=list)


_UNC_PREFIX = re.compile(r"^\\\\[?.]\\")  # \\?\ and \\.\ device prefixes


def _without_dots(parts: list[str]) -> list[str]:
    """Resolve `.` and `..` components so a path can never climb out of the destination."""
    out: list[str] = []
    for p in parts:
        if p == ".":
            continue
        if p == "..":
            if out:
                out.pop()
            continue
        out.append(p)
    return out


def folder_parts(ref: MediaRef) -> tuple[list[str], str]:
    """Split a source path into (folder components from the root, file name).

    Windows drive letters and UNC server/share names count as folder levels
    (`O:\\a\\b.mov` -> ['O', 'a']); `/Volumes/X/a/b.mov` -> ['Volumes', 'X', 'a'].
    """
    raw = ref.path
    if ref.path_style is PathStyle.WINDOWS:
        raw = _UNC_PREFIX.sub("", raw)
        raw = raw.replace("\\", "/")
        parts = [p for p in raw.split("/") if p]
        if parts and re.fullmatch(r"[A-Za-z]:", parts[0]):
            parts[0] = parts[0][0].upper()
    else:
        parts = [p for p in raw.split("/") if p]
    parts = _without_dots(parts)
    if not parts:
        raise ValueError(f"no file name in path {ref.path!r}")
    return parts[:-1], parts[-1]


def project_subfolder_parts(opts: PlanOptions) -> list[str]:
    """The wrapper folder as safe path components (no `.`/`..`, never absolute)."""
    return _without_dots([p for p in (opts.project_subfolder or "").split("/") if p])


def project_folder_parts(project_path: Path, opts: PlanOptions) -> list[str]:
    """Destination folder (relative to the destination root) for the project file itself: where its
    own source folder lands under the same layout rule as the media, so the project sits next to
    them (`.../Show/Show.prproj` next to `.../Show/MediaFiles/`)."""
    ref = MediaRef(path=canonical_posix(str(project_path)), path_style=PathStyle.POSIX)
    try:
        rel = dest_relative(ref, opts)
    except ValueError:
        return project_subfolder_parts(opts)
    return [p for p in posixpath.dirname(rel).split("/") if p]


def dest_relative(ref: MediaRef, opts: PlanOptions) -> str:
    folders, name = folder_parts(ref)
    if opts.preserve_after_levels is None:
        kept: list[str] = []
    else:
        kept = folders[opts.preserve_after_levels :]
    rel = posixpath.join(*kept, name) if kept else name
    sub = project_subfolder_parts(opts)
    if sub:
        rel = posixpath.join(*sub, rel)
    return rel


def select(project: Project, opts: PlanOptions) -> list[MediaRef]:
    def wanted(m: MediaRef) -> bool:
        if m.is_cache:
            return False  # never copy application cache
        if m.role is Role.PROXY and not opts.include_proxies:
            return False
        used = set(m.used_in)
        if opts.sequences is not None:
            in_selection = bool(used & set(opts.sequences))
        else:
            in_selection = bool(used)
        return in_selection or (opts.include_unused and not used)

    chosen = [m for m in project.media if wanted(m)]
    if opts.include_proxies:
        # A proxy belongs with its original: pull in pairs of selected originals, and only
        # keep proxies whose original is selected (or that are used themselves).
        by_path = {m.path: m for m in project.media}
        have = {m.path for m in chosen}
        for m in list(chosen):
            if m.role is Role.ORIGINAL:
                for pp in m.paired_paths:
                    if pp not in have and pp in by_path:
                        chosen.append(by_path[pp])
                        have.add(pp)
    return chosen


def build_plan(project: Project, opts: PlanOptions | None = None) -> Plan:
    opts = opts or PlanOptions()
    plan = Plan(skipped_cache=sum(1 for m in project.media if m.is_cache))
    taken: dict[str, str] = {}  # dest_rel (case-folded, APFS) -> source path
    for m in select(project, opts):
        try:
            rel = dest_relative(m, opts)
        except ValueError:
            plan.unusable.append(m.path)
            continue
        key = rel.casefold()
        if key in taken and taken[key] != m.path:
            stem, dot, ext = (
                rel.rpartition(".") if "." in posixpath.basename(rel) else (rel, "", "")
            )
            n = 2
            while f"{stem}_{n}{dot}{ext}".casefold() in taken:
                n += 1
            rel = f"{stem}_{n}{dot}{ext}"
            key = rel.casefold()
            plan.renamed_on_collision += 1
        taken[key] = m.path
        plan.copies.append(PlannedCopy(source=m, dest_rel=rel))
    return plan
