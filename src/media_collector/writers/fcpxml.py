"""FCPXML relink writer: rewrites `src` on `<media-rep>` (and legacy `<asset>`) elements.

Also handles `.fcpxmld` bundles (copies the bundle, rewrites its Info.fcpxml). Final Cut stores a
security-scoped `<bookmark>` (an encoded reference to the file's OLD location) inside each
`<media-rep>`. On a relinked entry that bookmark is stale, so it is removed and Final Cut falls back
to `src` — the same shape as exports that have no bookmarks (e.g. Resolve's), which is the case
verified in Final Cut. Bookmarks on entries that are NOT relinked are left untouched.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from xml.sax.saxutils import escape, unescape

from media_collector.paths import path_from_reference
from media_collector.writers import RelinkResult, copy_bundle, format_like, rewrite_text_file

_SRC = re.compile(r'(<(?:media-rep|asset)\b[^>]*?\bsrc\s*=\s*")([^"]*)(")', re.DOTALL)
_ENT = {"&apos;": "'", "&quot;": '"'}
# A media-rep with a body (not self-closing): opening tag, contents, closing tag.
_BLOCK = re.compile(
    r'(<media-rep\b[^>]*?\bsrc\s*=\s*"([^"]*)"[^>]*?(?<!/)>)(.*?)(</media-rep>)', re.DOTALL
)
_BOOKMARK = re.compile(r"[ \t]*<bookmark\b.*?</bookmark>[ \t]*\r?\n?", re.DOTALL)


def _relink_text(source: Path, out_dir: Path, path_map: dict[str, Path]):
    def transform(text: str, res: RelinkResult) -> str:
        new_srcs: set[str] = set()

        def sub(m: re.Match) -> str:
            raw = unescape(m.group(2), _ENT)
            ref = path_from_reference(raw, source.parent)
            res.media_objects += 1
            if ref is not None and ref[0] in path_map:
                res.relinked += 1
                new = format_like(raw, path_map[ref[0]], out_dir)
                new_srcs.add(new)
                return m.group(1) + escape(new, {'"': "&quot;"}) + m.group(3)
            if ref is not None and ref[0] not in res.left_unchanged:
                res.left_unchanged.append(ref[0])
            return m.group(0)

        text = _SRC.sub(sub, text)

        def drop_bookmark(m: re.Match) -> str:
            if unescape(m.group(2), _ENT) not in new_srcs or "<bookmark" not in m.group(3):
                return m.group(0)
            res.notes.append("removed_bookmark")
            return m.group(1) + _BOOKMARK.sub("", m.group(3)) + m.group(4)

        text = _BLOCK.sub(drop_bookmark, text)
        n = res.notes.count("removed_bookmark")
        res.notes[:] = [x for x in res.notes if x != "removed_bookmark"]
        if n:
            res.notes.append(
                f"Removed {n} stale media bookmark(s) from relinked entries; Final Cut uses the file "
                "path instead."
            )
        return text

    return transform


def relink_fcpxml(source: Path, output: Path, path_map: dict[str, Path]) -> RelinkResult:
    source, output = Path(source), Path(output)
    if not source.is_dir():
        return rewrite_text_file(
            source, output, _relink_text(source, output.resolve().parent, path_map)
        )
    copy_bundle(source, output)  # .fcpxmld bundle
    try:
        inner_src = source / "Info.fcpxml"
        inner_out = output / "Info.fcpxml"
        # rewrite in place inside the fresh copy via a temp sibling, then verify the bundle
        tmp = output / "Info.fcpxml.mc-src"
        inner_out.rename(tmp)
        try:
            res = rewrite_text_file(
                tmp, inner_out, _relink_text(inner_src, output.resolve(), path_map)
            )
        finally:
            tmp.unlink(missing_ok=True)
    except BaseException:  # never leave a half-built bundle that blocks the retry
        shutil.rmtree(output, ignore_errors=True)
        raise
    res.output = output
    return res
