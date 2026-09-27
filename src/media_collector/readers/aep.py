"""After Effects project (`.aep`) reader — read-only.

An `.aep` is a big-endian RIFX chunk container. Each footage item stores its location as a small JSON
record inside a chunk, e.g. `{"ascendcount_base":1,...,"fullpath":"/Users/x/a.mov","platform":2,...}`,
so the file paths can be found without decoding the whole chunk tree.

Limits: every footage item counts as used — which compositions use which footage is not read yet, so
the project has no sequences — and relinking an `.aep` (rewriting chunk sizes) is not
implemented (`RELINKABLE_FORMATS` leaves it out, so the app disables the option).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from media_collector.model import MediaRef, Project
from media_collector.paths import path_from_reference

_RECORD = re.compile(rb'\{"ascendcount_base"[^{}]*\}')


def read_aep(path: str | Path) -> Project:
    path = Path(path)
    data = path.read_bytes()
    if data[:4] != b"RIFX":
        raise ValueError("Not an After Effects project (missing RIFX header)")
    project = Project(source=str(path), format="aep")
    files: dict[str, MediaRef] = {}
    unreadable = 0
    for m in _RECORD.finditer(data):
        try:
            rec = json.loads(m.group().decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            unreadable += 1
            continue
        full = rec.get("fullpath")
        if not full or rec.get("target_is_folder"):
            continue
        ref = path_from_reference(full, path.parent)
        if ref is None:
            project.skipped_non_file_media += 1
            continue
        files.setdefault(
            ref[0],
            MediaRef(path=ref[0], path_style=ref[1], title=Path(ref[0].replace("\\", "/")).name),
        )
    if unreadable:
        project.warnings.append(
            f"{unreadable} footage record(s) in this project could not be read and are not included."
        )
    # No real sequences (compositions are not read yet): a synthetic id marks all footage as used.
    for mref in files.values():
        mref.used_in = ("project",)
    project.media = sorted(files.values(), key=lambda x: x.path)
    return project
