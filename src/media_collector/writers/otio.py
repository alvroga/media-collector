"""OTIO relink writer: rewrites only the value of `"target_url"` keys (JSON text substitution).

Keeps each reference in its original style (plain path, `file://` URL, or relative to the file).
Paths embedded elsewhere, e.g. in adapter `metadata` blocks, are not touched.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from media_collector.paths import path_from_reference
from media_collector.writers import RelinkResult, format_like, rewrite_text_file

_TARGET = re.compile(r'("target_url"\s*:\s*)("(?:[^"\\]|\\.)*")')


def relink_otio(source: Path, output: Path, path_map: dict[str, Path]) -> RelinkResult:
    def transform(text: str, res: RelinkResult) -> str:
        def sub(m: re.Match) -> str:
            raw = json.loads(m.group(2))
            ref = path_from_reference(raw, Path(source).parent)
            res.media_objects += 1
            if ref is not None and ref[0] in path_map:
                res.relinked += 1
                new = format_like(raw, path_map[ref[0]], Path(output).resolve().parent)
                return m.group(1) + json.dumps(new, ensure_ascii=False)
            if ref is not None and ref[0] not in res.left_unchanged:
                res.left_unchanged.append(ref[0])
            return m.group(0)

        return _TARGET.sub(sub, text)

    return rewrite_text_file(Path(source), Path(output), transform)
