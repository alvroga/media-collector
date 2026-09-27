"""OpenTimelineIO (`.otio`, JSON) reader — no dependency on the opentimelineio package.

Every `Timeline` is a sequence. A clip has a dictionary `media_references` with arbitrary keys plus
an `active_media_reference_key`; OTIO defines NO convention for which reference is a proxy (the
RV OTIO docs use keys like "Frames", "Movie", "Streaming"). So: a key containing "proxy" is
treated as a proxy (a heuristic, pairing it with the clip's other references), every other
reference is an original, and every reference of a clip counts as used — over-copying is safer
than missing an alternate. `active_media_reference_key` is currently ignored. Image-sequence
references are reported as warnings until supported.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from media_collector.model import MediaRef, Project, Role, Sequence
from media_collector.paths import path_from_reference


def read_otio(path: str | Path) -> Project:
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    project = Project(source=str(path), format="otio")
    files: dict[str, MediaRef] = {}
    used: dict[str, list[str]] = {}
    image_seqs = 0

    def schema(o: Any) -> str:
        return o.get("OTIO_SCHEMA", "").split(".")[0] if isinstance(o, dict) else ""

    timelines: list[dict] = []

    def find_timelines(o: Any) -> None:
        if schema(o) == "Timeline":
            timelines.append(o)
        elif isinstance(o, dict):
            for v in o.values():
                find_timelines(v)
        elif isinstance(o, list):
            for v in o:
                find_timelines(v)

    find_timelines(data)
    if not timelines:  # a bare Stack/Track/Clip file: treat the whole document as one sequence
        timelines = [data]

    def clip_refs(clip: dict) -> dict[str, dict]:
        refs = clip.get("media_references")
        if isinstance(refs, dict) and refs:
            return refs
        ref = clip.get("media_reference")
        return {"DEFAULT_MEDIA": ref} if isinstance(ref, dict) else {}

    for n, tl in enumerate(timelines):
        sid = f"timeline-{n + 1}"
        project.sequences.append(Sequence(sid, tl.get("name") or path.stem))

        def walk(o: Any, sid: str = sid) -> None:
            nonlocal image_seqs
            if schema(o) == "Clip":
                per_clip: dict[Role, list[str]] = {Role.ORIGINAL: [], Role.PROXY: []}
                for key, ref in clip_refs(o).items():
                    kind = schema(ref)
                    if kind == "ImageSequenceReference":
                        image_seqs += 1
                        continue
                    if kind != "ExternalReference":
                        continue
                    r = path_from_reference(ref.get("target_url", ""), path.parent)
                    if r is None:
                        project.skipped_non_file_media += 1
                        continue
                    role = Role.PROXY if "proxy" in key.lower() else Role.ORIGINAL
                    m = files.setdefault(
                        r[0],
                        MediaRef(
                            path=r[0],
                            path_style=r[1],
                            role=role,
                            title=Path(r[0].replace("\\", "/")).name,
                        ),
                    )
                    per_clip[role].append(m.path)
                    if sid not in used.setdefault(m.path, []):
                        used[m.path].append(sid)
                for o_path in per_clip[Role.ORIGINAL]:
                    for p_path in per_clip[Role.PROXY]:
                        if p_path not in files[o_path].paired_paths:
                            files[o_path].paired_paths += (p_path,)
                        if o_path not in files[p_path].paired_paths:
                            files[p_path].paired_paths += (o_path,)
            elif isinstance(o, dict):
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)

        walk(tl)
    for m in files.values():
        m.used_in = tuple(used.get(m.path, ()))
    if image_seqs:
        project.warnings.append(
            f"{image_seqs} image-sequence reference(s) were skipped: image sequences are not supported"
        )
    project.media = sorted(files.values(), key=lambda m: m.path)
    return project
