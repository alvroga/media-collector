"""Final Cut Pro 7 XML (xmeml) reader — also what Premiere and Resolve export as "Final Cut Pro XML".

Media are `<file id=...>` elements; the first occurrence carries `<pathurl>`, later ones are bare
`<file id=.../>` references, so ids are resolved globally. Every top-level `<sequence>` is a
sequence; nested sequences (inside a `<clipitem>`) count as part of their parent. Files that only
appear in bins, not in any sequence, are "in project, unused". This format carries no proxy info.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from media_collector.model import MediaRef, Project, Sequence
from media_collector.paths import path_from_reference


def read_fcp7xml(path: str | Path) -> Project:
    path = Path(path)
    root = ET.parse(path).getroot()
    project = Project(source=str(path), format="fcp7xml")

    parent = {c: p for p in root.iter() for c in p}

    def nested(e: ET.Element) -> bool:
        p = parent.get(e)
        while p is not None:
            if p.tag in ("clipitem", "sequence"):
                return True
            p = parent.get(p)
        return False

    urls: dict[str, str] = {}
    for f in root.iter("file"):
        pu = f.findtext("pathurl")
        if f.get("id") and pu:
            urls[f.get("id")] = pu

    files: dict[str, MediaRef] = {}
    skipped = 0
    for url in urls.values():
        ref = path_from_reference(url, path.parent)
        if ref is None:
            skipped += 1
            continue
        p, style = ref
        files.setdefault(
            p, MediaRef(path=p, path_style=style, title=Path(p.replace("\\", "/")).name)
        )
    project.skipped_non_file_media = skipped
    by_id = {
        fid: files[r[0]] for fid, u in urls.items() if (r := path_from_reference(u, path.parent))
    }

    used: dict[str, list[str]] = {}
    for n, seq in enumerate(e for e in root.iter("sequence") if not nested(e)):
        sid = seq.get("id") or f"seq-{n + 1}"
        project.sequences.append(Sequence(sid, seq.findtext("name") or sid))
        for f in seq.iter("file"):
            m = by_id.get(f.get("id") or "")
            if m is not None and sid not in used.setdefault(m.path, []):
                used[m.path].append(sid)
    for m in files.values():
        m.used_in = tuple(used.get(m.path, ()))
    project.media = sorted(files.values(), key=lambda m: m.path)
    return project
