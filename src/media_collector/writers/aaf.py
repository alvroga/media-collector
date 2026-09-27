"""AAF relink writer (pyaaf2): copies the AAF, then rewrites each file locator's `URLString`.

The source is never touched. The rewritten file is re-read and checked, but has not been verified in
editing applications (Premiere, Resolve, Avid) — the result carries a note saying so.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from media_collector.fsutil import move_no_clobber
from media_collector.paths import path_from_reference
from media_collector.readers.aaf import iter_locators
from media_collector.writers import RelinkResult, check_targets, format_like, verify


def relink_aaf(source: Path, output: Path, path_map: dict[str, Path]) -> RelinkResult:
    import aaf2

    source, output = Path(source), Path(output)
    check_targets(source, output)
    res = RelinkResult(output=output)
    out_dir = output.resolve().parent
    partial = output.with_name(output.name + ".mc-partial")
    shutil.copyfile(source, partial)
    try:
        with aaf2.open(str(partial), "r+") as f:
            for sm in f.content.sourcemobs():
                for loc in iter_locators(sm):
                    try:
                        raw = loc["URLString"].value
                    except (KeyError, AttributeError):
                        continue
                    ref = path_from_reference(raw, source.parent)
                    res.media_objects += 1
                    if ref is not None and ref[0] in path_map:
                        loc["URLString"].value = format_like(raw, path_map[ref[0]], out_dir)
                        res.relinked += 1
                    elif ref is not None and ref[0] not in res.left_unchanged:
                        res.left_unchanged.append(ref[0])
        move_no_clobber(partial, output)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    res.notes.append(
        "AAF locators were rewritten with pyaaf2; the file re-reads correctly but has not been "
        "verified in Premiere, Resolve or Avid."
    )
    verify(output, res)
    return res
