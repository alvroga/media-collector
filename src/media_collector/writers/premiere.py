"""Premiere `.prproj` relink writer. Format notes: docs/agent_docs/prproj-format.md

Streams the decompressed XML line by line and rewrites only path fields inside top-level
`<Media>` objects (`FilePath`, `ActualMediaFilePath`, `RelativePath`, `MediaFileHistory<n>`) plus
the project's own `lastknowngoodprojectpath`. Everything else passes through byte-for-byte.
The source project is never touched; the output must not already exist.
"""

from __future__ import annotations

import gzip
import os
import re
from pathlib import Path
from xml.sax.saxutils import escape, unescape

from media_collector.fsutil import move_no_clobber
from media_collector.model import detect_path_style
from media_collector.paths import normalize_path
from media_collector.writers import RelinkResult, verify

_FIELD = re.compile(
    rb"^(\t+)<(FilePath|ActualMediaFilePath|RelativePath|MediaFileHistory\d+)>(.*)</\2>(\r?\n?)$"
)
_PROJECT_PATH = re.compile(
    rb"^(\s*)<project\.settings\.lastknowngoodprojectpath>.*</project\.settings\.lastknowngoodprojectpath>(\r?\n?)$"
)
_ABS_FIELDS = {b"FilePath", b"ActualMediaFilePath"}


def _canonical(p: str) -> str:
    """Same spelling the reader uses, so path-map lookups match (boot-volume aliases)."""
    style = detect_path_style(p)
    return normalize_path(p, style) if style is not None else p


def _dec(b: bytes) -> str:
    return unescape(b.decode("utf-8"), {"&apos;": "'", "&quot;": '"'})


def _enc(s: str) -> bytes:
    return escape(s).encode("utf-8")


def _relative(new_abs: Path, project_dir: Path) -> str:
    rel = os.path.relpath(new_abs, project_dir)
    return rel if rel.startswith("..") else "./" + rel


def _relink_media_block(
    lines: list[bytes], path_map: dict[str, Path], project_dir: Path, res: RelinkResult
) -> list[bytes]:
    res.media_objects += 1
    abs_values = {}
    for ln in lines:
        m = _FIELD.match(ln)
        if m and m.group(2) in _ABS_FIELDS:
            abs_values[m.group(2)] = _canonical(_dec(m.group(3)))
    old = next(
        (
            abs_values[k]
            for k in (b"ActualMediaFilePath", b"FilePath")
            if abs_values.get(k) in path_map
        ),
        None,
    )
    if old is None:
        if any(v for v in abs_values.values()):
            res.left_unchanged.append(next(iter(abs_values.values())))
        return lines
    new = path_map[old]
    res.relinked += 1
    out = []
    for ln in lines:
        m = _FIELD.match(ln)
        if not m:
            out.append(ln)
            continue
        indent, name, _, eol = m.group(1), m.group(2), m.group(3), m.group(4)
        if name == b"RelativePath":
            val = _relative(new, project_dir)
        else:  # FilePath, ActualMediaFilePath, MediaFileHistory<n>
            val = str(new)
        out.append(indent + b"<" + name + b">" + _enc(val) + b"</" + name + b">" + eol)
    return out


def relink_premiere(source: Path, output: Path, path_map: dict[str, Path]) -> RelinkResult:
    """Write `output` = `source` with media paths remapped via `path_map` (old path -> new path)."""
    source, output = Path(source), Path(output)
    if output.resolve() == source.resolve():
        raise ValueError("output must differ from the source project")
    if output.exists():
        raise FileExistsError(f"refusing to overwrite {output}")
    project_dir = output.resolve().parent
    res = RelinkResult(output=output)
    partial = output.with_name(output.name + ".mc-partial")
    block: list[bytes] | None = None
    try:
        with gzip.open(source, "rb") as fin, gzip.open(partial, "wb", compresslevel=6) as fout:
            for line in iter(fin.readline, b""):
                if block is not None:
                    block.append(line)
                    if line.startswith(b"\t</Media>"):
                        for ln in _relink_media_block(block, path_map, project_dir, res):
                            fout.write(ln)
                        block = None
                    continue
                if line.startswith(b"\t<Media ") and not line.rstrip().endswith(b"/>"):
                    block = [line]
                    continue
                m = _PROJECT_PATH.match(line)
                if m:
                    line = (
                        m.group(1)
                        + b"<project.settings.lastknowngoodprojectpath>"
                        + _enc(str(output.resolve()))
                        + b"</project.settings.lastknowngoodprojectpath>"
                        + m.group(2)
                    )
                fout.write(line)
            if block is not None:  # unterminated Media object: pass through unchanged
                for ln in block:
                    fout.write(ln)
        move_no_clobber(partial, output)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    verify(output, res)
    return res
