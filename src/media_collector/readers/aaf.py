"""AAF reader (uses `pyaaf2`, pure Python).

A composition mob is a sequence. Its slots hold segments (Sequence, NestedScope, OperationGroup,
Selector...) containing SourceClips that point at master mobs, which link down through source mobs
to a file source mob whose descriptor has `NetworkLocator`s (`URLString`, normally `file://`).
Usage is found by following that chain from each composition.

Not handled (reported as warnings, never silently dropped): essence embedded in the AAF or managed
by Avid (no locator: files are located by MobID/UMID in MXF folders, a separate feature).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from media_collector.model import MediaRef, Project, Sequence
from media_collector.paths import path_from_reference

_FILE_DESCRIPTORS = {
    "CDCIDescriptor",
    "RGBADescriptor",
    "DigitalImageDescriptor",
    "PCMDescriptor",
    "WAVEDescriptor",
    "SoundDescriptor",
    "AIFCDescriptor",
    "MPEGVideoDescriptor",
    "FileDescriptor",
}


def iter_locators(mob: Any) -> list[Any]:
    """File locator objects on a source mob's descriptor (also inside multi-descriptors)."""
    try:
        desc = mob.descriptor
    except (AttributeError, KeyError):
        return []
    if desc is None:
        return []
    descs = [desc, *(getattr(desc, "file_descriptors", None) or [])]
    return [loc for d in descs for loc in (getattr(d, "locator", None) or [])]


def _locator_urls(mob: Any) -> list[str]:
    """`URLString`s of the file locators on a source mob."""
    urls = []
    for loc in iter_locators(mob):
        try:
            urls.append(loc["URLString"].value)
        except (KeyError, AttributeError):
            continue
    return urls


def _children(seg: Any) -> list[Any]:
    out: list[Any] = []
    for attr in ("components", "segments", "input_segments", "slots", "alternates"):
        v = getattr(seg, attr, None)
        if v:
            for it in v:
                out.append(getattr(it, "segment", it))
    sel = getattr(seg, "selected", None)
    if sel is not None:
        out.append(sel)
    return out


def read_aaf(path: str | Path) -> Project:
    try:
        import aaf2
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("Reading AAF needs the 'pyaaf2' package") from e

    path = Path(path)
    project = Project(source=str(path), format="aaf")
    files: dict[str, MediaRef] = {}
    mob_paths: dict[Any, list[str]] = {}

    try:
        handle = aaf2.open(str(path), "r")
    except Exception as e:
        raise ValueError(f"Not a readable AAF file: {e}") from e
    with handle as f:
        content = f.content
        embedded = 0
        for sm in content.sourcemobs():
            urls = _locator_urls(sm)
            paths = []
            for u in urls:
                ref = path_from_reference(u, path.parent)
                if ref is None:
                    project.skipped_non_file_media += 1
                    continue
                m = files.setdefault(
                    ref[0],
                    MediaRef(
                        path=ref[0], path_style=ref[1], title=Path(ref[0].replace("\\", "/")).name
                    ),
                )
                paths.append(m.path)
            if paths:
                mob_paths[sm.mob_id] = paths
            elif not urls and type(getattr(sm, "descriptor", None)).__name__ in _FILE_DESCRIPTORS:
                embedded += 1

        memo: dict[Any, set[str]] = {}

        def media_of(mob: Any, visiting: frozenset = frozenset()) -> set[str]:
            key = mob.mob_id
            if key in mob_paths:
                return set(mob_paths[key])
            if key in memo:
                return memo[key]
            if key in visiting:
                return set()
            found: set[str] = set()
            for slot in mob.slots:
                stack = [slot.segment]
                while stack:
                    seg = stack.pop()
                    if seg is None:
                        continue
                    if type(seg).__name__ == "SourceClip":
                        target = seg.mob
                        if target is not None:
                            found |= media_of(target, visiting | {key})
                    else:
                        stack.extend(_children(seg))
            memo[key] = found
            return found

        comps = list(content.toplevel()) or list(content.compositionmobs())
        used: dict[str, list[str]] = {}
        for comp in comps:
            if type(comp).__name__ != "CompositionMob":
                continue
            sid = str(comp.mob_id)
            project.sequences.append(Sequence(sid, comp.name or sid))
            for p in media_of(comp):
                if sid not in used.setdefault(p, []):
                    used[p].append(sid)
        if embedded:
            project.warnings.append(
                f"{embedded} media item(s) have no external file location (embedded in the AAF or "
                "managed by Avid) and were skipped"
            )
    for m in files.values():
        m.used_in = tuple(used.get(m.path, ()))
    project.media = sorted(files.values(), key=lambda m: m.path)
    return project
