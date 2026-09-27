"""Relink writers. Each writes a NEW project file whose media paths point at the copies.

Shared pieces live here: the result type, the reference formatter (keep the original's style:
`file://` URL, plain absolute path, or path relative to the project), a text-rewrite driver, and
the format dispatcher `relink_project`. Sources are never touched; outputs are never overwritten.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

from media_collector.fsutil import move_no_clobber
from media_collector.model import PathStyle, detect_path_style

# Formats `relink_project` can write. The app disables the relink option for everything else.
RELINKABLE_FORMATS = frozenset({"premiere", "fcp7xml", "fcpxml", "otio", "aaf"})


@dataclass
class RelinkResult:
    output: Path
    media_objects: int = 0
    relinked: int = 0
    # Original paths that were not in the path map and still point at the old location.
    left_unchanged: list[str] = field(default_factory=list)
    # After writing: relinked paths that do not exist on disk (verification failures).
    missing_after: list[str] = field(default_factory=list)
    # Things the user should know (e.g. data we deliberately left untouched).
    notes: list[str] = field(default_factory=list)


def relinked_name(name: str) -> str:
    """`Show.prproj` -> `Show_relinked.prproj` (also for bundles: `Show.fcpxmld`)."""
    p = Path(name)
    return f"{p.stem}_relinked{p.suffix}"


def format_like(original: str, new: Path, output_dir: Path) -> str:
    """Write `new` in the same style as the reference it replaces."""
    low = original.lower()
    if low.startswith("file:"):
        prefix = "file://localhost" if low.startswith("file://localhost") else "file://"
        return prefix + quote(str(new), safe="/")
    if detect_path_style(original) is None and "://" not in original:  # relative path
        return os.path.relpath(new, output_dir)
    return str(new)


def check_targets(source: Path, output: Path) -> None:
    if output.resolve() == source.resolve():
        raise ValueError("output must differ from the source project")
    if output.exists():
        raise FileExistsError(f"refusing to overwrite {output}")


def rewrite_text_file(
    source: Path, output: Path, transform: Callable[[str, RelinkResult], str]
) -> RelinkResult:
    """Apply `transform` to a UTF-8 text project, write it atomically, verify by re-reading."""
    check_targets(source, output)
    res = RelinkResult(output=output)
    text = Path(source).read_bytes().decode("utf-8")
    partial = output.with_name(output.name + ".mc-partial")
    try:
        partial.write_bytes(transform(text, res).encode("utf-8"))
        move_no_clobber(partial, output)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    verify(output, res)
    return res


def verify(output: Path, res: RelinkResult) -> None:
    """Re-read the written project with the normal reader; every local file must exist."""
    """The written file stays in place either way; a failure to re-read it becomes a note."""
    from media_collector.readers import read_project

    try:
        media = read_project(output).media
    except Exception as e:  # noqa: BLE001 - reported, not fatal: the output is already written
        res.notes.append(
            f"The relinked project was written but could not be re-read to verify it "
            f"({type(e).__name__}: {e}); check it before relying on it."
        )
        return
    for m in media:
        if not m.is_cache and m.path_style is PathStyle.POSIX and not Path(m.path).exists():
            res.missing_after.append(m.path)


def relink_project(source: Path, output: Path, path_map: dict) -> RelinkResult:
    """Write a relinked copy of `source` to `output`; dispatches on the project's format."""
    source = Path(source)
    suffix = source.suffix.lower()
    if suffix == ".prproj":
        from media_collector.writers.premiere import relink_premiere

        return relink_premiere(source, output, path_map)
    if suffix == ".aaf":
        from media_collector.writers.aaf import relink_aaf

        return relink_aaf(source, output, path_map)
    if suffix == ".otio":
        from media_collector.writers.otio import relink_otio

        return relink_otio(source, output, path_map)
    if suffix in (".fcpxml", ".fcpxmld"):
        from media_collector.writers.fcpxml import relink_fcpxml

        return relink_fcpxml(source, output, path_map)
    if suffix == ".xml":
        from media_collector.readers import _xml_root_tag

        tag = _xml_root_tag(source)
        if tag == "xmeml":
            from media_collector.writers.fcp7xml import relink_fcp7xml

            return relink_fcp7xml(source, output, path_map)
        if tag == "fcpxml":
            from media_collector.writers.fcpxml import relink_fcpxml

            return relink_fcpxml(source, output, path_map)
    raise ValueError(f"Relinking is not supported for {source.suffix or 'this format'} projects")


def copy_bundle(source: Path, output: Path) -> None:
    """Copy a bundle directory (e.g. .fcpxmld) to a new location, refusing to overwrite."""
    check_targets(source, output)
    shutil.copytree(source, output)
