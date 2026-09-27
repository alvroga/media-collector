"""Turning a project's path string into a local macOS path (ADR-0004).

POSIX paths are used as-is. Windows-authored paths need a user-supplied mapping of drive
letter / UNC share to a local folder, e.g. {"O:": "/Volumes/Media", "//nas/share": "/Volumes/share"}.
Unmapped foreign paths resolve to None (reported by the caller, never guessed).
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import unquote, urlparse

from media_collector.model import MediaRef, PathStyle, detect_path_style

_DEVICE_PREFIX = re.compile(r"^\\\\[?.]\\")


def _norm_key(key: str) -> str:
    return key.replace("\\", "/").rstrip("/").lower()


# --- macOS boot-volume aliases ----------------------------------------------------------------
# The same file is spelled `/Users/x/a.mov`, `/Volumes/Macintosh HD/Users/x/a.mov` (the boot volume
# appears in /Volumes as a symlink to `/`) and `/System/Volumes/Data/Users/x/a.mov` (Apple's firmlink).
# All readers/writers use the plain `/x` form so a file is never seen twice.
_BOOT_DEFAULTS = ("Macintosh HD", "Macintosh HD - Data")
_DATA_FIRMLINK = "/System/Volumes/Data"


def _compute_alias_names(volumes: Path) -> frozenset[str]:
    """Names (casefolded) under /Volumes that mean the boot volume. Names of volumes that are
    mounted here and are NOT the boot volume are never aliases; the default Apple names count
    as aliases when nothing by that name is mounted here (a project from another Mac)."""
    names: set[str] = set()
    present: set[str] = set()
    if volumes.is_dir():
        for e in volumes.iterdir():
            present.add(e.name.casefold())
            if os.path.realpath(e) in ("/", _DATA_FIRMLINK):
                names.add(e.name.casefold())
    names |= {d.casefold() for d in _BOOT_DEFAULTS if d.casefold() not in present}
    return frozenset(names)


@lru_cache(maxsize=1)
def _alias_names() -> frozenset[str]:
    return _compute_alias_names(Path("/Volumes"))


def canonical_posix(path: str) -> str:
    """`/Volumes/<boot volume>/x` and `/System/Volumes/Data/x` -> `/x`; anything else unchanged."""
    if path == _DATA_FIRMLINK or path.startswith(_DATA_FIRMLINK + "/"):
        return path[len(_DATA_FIRMLINK) :] or "/"
    parts = path.split("/")
    if (
        len(parts) >= 3
        and parts[0] == ""
        and parts[1] == "Volumes"
        and parts[2].casefold() in _alias_names()
    ):
        return "/" + "/".join(parts[3:])
    return path


def normalize_path(path: str, style: PathStyle) -> str:
    """Canonical spelling of a project path (only POSIX paths have aliases)."""
    return canonical_posix(path) if style is PathStyle.POSIX else path


def resolve_source(ref: MediaRef, mappings: dict[str, str] | None = None) -> Path | None:
    """Local path for a project's media reference, or None if it cannot be located.

    `mappings` maps a prefix in the project to a local folder: a Windows drive/share
    (`"O:"`, `"//nas/share"`) or a folder on another Mac (`"/Users/demo/Movies/Lib.fcpbundle"`).
    Longest prefix wins; matching is case-insensitive and on whole path components. POSIX paths
    with no matching mapping are used as they are; unmapped Windows paths give None."""
    maps = {
        _norm_key(canonical_posix(k) if k.startswith("/") else k): v
        for k, v in (mappings or {}).items()
    }
    if ref.path_style is PathStyle.POSIX:
        raw = canonical_posix(ref.path)
    else:
        raw = _DEVICE_PREFIX.sub("", ref.path).replace("\\", "/")
    for prefix in sorted(maps, key=len, reverse=True):
        if raw.lower() == prefix or raw.lower().startswith(prefix + "/"):
            return Path(maps[prefix]) / raw[len(prefix) :].lstrip("/")
    return Path(canonical_posix(ref.path)) if ref.path_style is PathStyle.POSIX else None


def foreign_prefix(ref: MediaRef) -> str | None:
    """Drive/share prefix of a Windows-style path in mapping-key form (`O:` or `//server/share`),
    or None for POSIX paths. Used to ask the user which local folder each prefix maps to."""
    if ref.path_style is PathStyle.POSIX:
        return None
    raw = _DEVICE_PREFIX.sub("", ref.path).replace("\\", "/")
    if raw.startswith("//"):
        parts = [p for p in raw.split("/") if p]
        return "//" + "/".join(parts[:2])
    return raw[:2].upper() if len(raw) >= 2 and raw[1] == ":" else None


def _path_from_reference(value: str, base_dir: Path | None = None) -> tuple[str, PathStyle] | None:
    """Turn a media reference from an exchange file into (path, style), or None if it is not a
    local file (http URLs, bare numbers, empty). Accepts plain paths and `file://` URLs
    (percent-decoded; `file:///C:/x` and `file://server/share/x` become Windows paths).
    A relative path is resolved against `base_dir` when given."""
    value = (value or "").strip()
    if not value:
        return None
    if value.lower().startswith("file:"):
        u = urlparse(value)
        path = unquote(u.path)
        host = u.netloc
        if host and host.lower() != "localhost":
            return "\\\\" + host + path.replace("/", "\\"), PathStyle.WINDOWS  # UNC
        if re.match(r"^/[A-Za-z]:", path):
            return path[1:].replace("/", "\\"), PathStyle.WINDOWS
        value = path
    style = detect_path_style(value)
    if style is not None:
        return value, style
    if base_dir is not None and "://" not in value and not value.isdigit():
        return str((base_dir / value).resolve()), PathStyle.POSIX
    return None


def path_from_reference(value: str, base_dir: Path | None = None) -> tuple[str, PathStyle] | None:
    """As `_path_from_reference`, with POSIX paths in their canonical (alias-free) spelling."""
    r = _path_from_reference(value, base_dir)
    return None if r is None else (normalize_path(r[0], r[1]), r[1])
