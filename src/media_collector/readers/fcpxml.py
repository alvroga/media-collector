"""Final Cut Pro X / FCPXML reader (1.x), including `.fcpxmld` bundles (read via Info.fcpxml).

Assets live in `<resources>`; each `<project>` is a sequence and uses assets through `ref`
attributes, following `<media>` resources (compound clips, multicams) transitively. Paths come from
`<media-rep src=...>` (`kind="original-media"` / `"proxy-media"`) or the legacy `asset/@src`.
Proxies are paired with the original of the same asset.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from media_collector.model import MediaRef, Project, Role, Sequence
from media_collector.paths import path_from_reference


def read_fcpxml(path: str | Path) -> Project:
    path = Path(path)
    root = ET.parse(path).getroot()
    project = Project(source=str(path), format="fcpxml")
    res_el = root.find("resources")
    resources = {e.get("id"): e for e in (res_el if res_el is not None else []) if e.get("id")}

    files: dict[str, MediaRef] = {}
    asset_paths: dict[str, list[str]] = {}  # asset id -> paths of its reps (original + proxy)

    def add(p: str, style, role: Role, title: str) -> str:
        m = files.setdefault(p, MediaRef(path=p, path_style=style, role=role, title=title))
        return m.path

    for aid, a in resources.items():
        if a.tag != "asset":
            continue
        reps = [(r.get("kind", "original-media"), r.get("src", "")) for r in a.findall("media-rep")]
        if not reps and a.get("src"):
            reps = [("original-media", a.get("src", ""))]
        orig, prox = [], []
        for kind, src in reps:
            ref = path_from_reference(src, path.parent)
            if ref is None:
                project.skipped_non_file_media += 1
                continue
            role = Role.PROXY if kind == "proxy-media" else Role.ORIGINAL
            p = add(ref[0], ref[1], role, a.get("name") or Path(ref[0].replace("\\", "/")).name)
            asset_paths.setdefault(aid, []).append(p)
            (prox if role is Role.PROXY else orig).append(p)
        for o in orig:
            for x in prox:
                files[o].paired_paths += (x,)
                files[x].paired_paths += (o,)

    def collect(elem: ET.Element, out: set[str], seen: set[str]) -> None:
        for e in elem.iter():
            r = e.get("ref")
            if not r or r not in resources or r in seen:
                continue
            seen.add(r)
            target = resources[r]
            if target.tag == "asset":
                out.add(r)
            else:  # compound clip / multicam `media` resource: follow into it
                collect(target, out, seen)

    projects = list(root.iter("project"))
    sequences = projects or [root]
    used: dict[str, list[str]] = {}
    for n, proj in enumerate(sequences):
        sid = proj.get("uid") or f"project-{n + 1}"
        project.sequences.append(Sequence(sid, proj.get("name") or path.stem))
        assets: set[str] = set()
        collect(proj, assets, set())
        for aid in assets:
            for p in asset_paths.get(aid, []):
                if sid not in used.setdefault(p, []):
                    used[p].append(sid)
    for m in files.values():
        m.used_in = tuple(used.get(m.path, ()))
    project.media = sorted(files.values(), key=lambda m: m.path)
    return project
