"""Premiere Pro `.prproj` reader. Format notes: docs/agent_docs/prproj-format.md

The file is gzipped XML whose top-level children are objects linked by ObjectRef/ObjectURef.
Large projects are ~1 GB of XML, so it is stream-parsed one top-level object at a time.

Approach: keep only (a) every Media object's path fields, (b) original<->proxy pairs from
MediaSource/Content/ProxyMedia, (c) the ref edges between objects. "Media used by sequence X"
is everything reachable from X by following refs.
"""

from __future__ import annotations

import gzip
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

from media_collector.model import MediaRef, Project, Role, Sequence, detect_path_style
from media_collector.paths import normalize_path

_intern = sys.intern

# Adobe's fixed cache locations/extensions (matched case-insensitively). A path is cache if any
# folder component matches, or the file has a cache extension. Extend as new cases turn up.
_CACHE_DIR = re.compile(
    r"^(adobe premiere pro (video|audio) previews|.*\.prv|media cache( files)?|"
    r"adobe media cache|conformed audio|adobe after effects .*disk cache.*)$",
    re.IGNORECASE,
)
_CACHE_EXT = (".pek", ".cfa", ".ims", ".mcdb")


def is_premiere_cache(path: str) -> bool:
    parts = [p for p in re.split(r"[\\/]", path) if p]
    return path.lower().endswith(_CACHE_EXT) or any(_CACHE_DIR.match(p) for p in parts[:-1])


def _ref(el: ET.Element) -> str | None:
    if (v := el.get("ObjectRef")) is not None:
        return _intern("i" + v)
    if (v := el.get("ObjectURef")) is not None:
        return _intern("u" + v)
    return None


def read_premiere(path: str | Path) -> Project:
    path = Path(path)
    tags: dict[str, str] = {}
    edges: dict[str, list[str]] = defaultdict(list)
    media_fields: dict[str, dict[str, str]] = {}
    pairs: list[tuple[str, str]] = []  # (original media key, proxy media key)
    sequences: list[tuple[str, str]] = []  # (key, name)

    with gzip.open(path, "rb") as fh:
        depth = 0
        for event, el in ET.iterparse(fh, events=("start", "end")):
            if event == "start":
                depth += 1
                continue
            depth -= 1
            if depth != 1:
                continue  # only act on complete top-level children of <PremiereData>
            if (oid := el.get("ObjectID")) is not None:
                key = _intern("i" + oid)
            elif (uid := el.get("ObjectUID")) is not None:
                key = _intern("u" + uid)
            else:
                el.clear()
                continue
            tags[key] = el.tag
            out = edges[key]
            for sub in el.iter():
                if sub is not el and (r := _ref(sub)):
                    out.append(r)
            if el.tag == "Media":
                media_fields[key] = {
                    "path": el.findtext("ActualMediaFilePath") or el.findtext("FilePath") or "",
                    "title": el.findtext("Title") or "",
                    "relative": el.findtext("RelativePath") or "",
                    "offline": el.findtext("OfflineReason") or "",
                }
            elif el.tag in ("VideoMediaSource", "AudioMediaSource"):
                orig = el.find("MediaSource/Media")
                prox = el.find("MediaSource/Content/ProxyMedia")
                if orig is not None and prox is not None:
                    o, p = _ref(orig), _ref(prox)
                    if o and p:
                        pairs.append((o, p))
            elif el.tag == "Sequence":
                sequences.append((key, el.findtext("Name") or ""))
            el.clear()

    # Resolve each Media object to a distinct file (many Media objects share one path).
    project = Project(
        source=str(path), format="premiere", sequences=[Sequence(k[1:], n) for k, n in sequences]
    )
    by_path: dict[str, MediaRef] = {}
    key_to_path: dict[str, str] = {}
    proxy_keys = {p for _, p in pairs}
    for key, f in media_fields.items():
        style = detect_path_style(f["path"])
        if style is None:
            project.skipped_non_file_media += 1
            continue
        mpath = normalize_path(f["path"], style)
        key_to_path[key] = mpath
        ref = by_path.get(mpath)
        if ref is None:
            by_path[mpath] = MediaRef(
                path=mpath,
                path_style=style,
                role=Role.PROXY if key in proxy_keys else Role.ORIGINAL,
                title=f["title"],
                relative_path=f["relative"],
                is_cache=is_premiere_cache(mpath),
                offline_when_saved=f["offline"] not in ("", "0"),
            )
    for o, p in pairs:
        if o in key_to_path and p in key_to_path:
            op, pp = key_to_path[o], key_to_path[p]
            if by_path[op].role is Role.ORIGINAL and by_path[pp].role is Role.PROXY:
                if pp not in by_path[op].paired_paths:
                    by_path[op].paired_paths += (pp,)
                if op not in by_path[pp].paired_paths:
                    by_path[pp].paired_paths += (op,)

    # Usage: everything reachable from each sequence.
    used: dict[str, list[str]] = defaultdict(list)
    for seq_key, _name in sequences:
        seq_id = seq_key[1:]
        seen: set[str] = set()
        stack = [seq_key]
        while stack:
            k = stack.pop()
            if k in seen:
                continue
            seen.add(k)
            if k in key_to_path and seq_id not in used[key_to_path[k]]:
                used[key_to_path[k]].append(seq_id)
            stack.extend(edges.get(k, ()))
    for p, ref in by_path.items():
        ref.used_in = tuple(used.get(p, ()))

    project.media = sorted(by_path.values(), key=lambda m: m.path)
    return project
