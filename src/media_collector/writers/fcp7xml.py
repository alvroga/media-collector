"""FCP7 XML (xmeml) relink writer: rewrites only the text of `<pathurl>` elements."""

from __future__ import annotations

import re
from pathlib import Path
from xml.sax.saxutils import escape, unescape

from media_collector.paths import path_from_reference
from media_collector.writers import RelinkResult, format_like, rewrite_text_file

_PATHURL = re.compile(r"(<pathurl>)(.*?)(</pathurl>)", re.DOTALL)
_ENT = {"&apos;": "'", "&quot;": '"'}


def relink_fcp7xml(source: Path, output: Path, path_map: dict[str, Path]) -> RelinkResult:
    def transform(text: str, res: RelinkResult) -> str:
        def sub(m: re.Match) -> str:
            raw = unescape(m.group(2).strip(), _ENT)
            ref = path_from_reference(raw, Path(source).parent)
            res.media_objects += 1
            if ref is not None and ref[0] in path_map:
                res.relinked += 1
                new = format_like(raw, path_map[ref[0]], Path(output).resolve().parent)
                return m.group(1) + escape(new) + m.group(3)
            if ref is not None and ref[0] not in res.left_unchanged:
                res.left_unchanged.append(ref[0])
            return m.group(0)

        return _PATHURL.sub(sub, text)

    return rewrite_text_file(Path(source), Path(output), transform)
