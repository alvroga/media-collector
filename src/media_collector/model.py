"""Format-agnostic media-reference model.

Every reader emits a `Project`; the copy engine and relink writers consume only this.
Paths are kept exactly as found in the project file, tagged with their original OS style
(ADR-0004) — never converted to host `Path` objects.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

_WINDOWS_PATH = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\)")


class PathStyle(str, Enum):
    POSIX = "posix"
    WINDOWS = "windows"


class Role(str, Enum):
    ORIGINAL = "original"
    PROXY = "proxy"


def detect_path_style(raw: str) -> PathStyle | None:
    """Return the style of a file path string, or None if it isn't a file path at all
    (e.g. Premiere's synthetic media store a bare number)."""
    if raw.startswith("/"):
        return PathStyle.POSIX
    if _WINDOWS_PATH.match(raw):
        return PathStyle.WINDOWS
    return None


@dataclass(frozen=True)
class Sequence:
    """A sequence/timeline. Names are not unique (16 of 222 collide in one real project), so
    selection is always by `id` (a stable per-project identifier from the source format)."""

    id: str
    name: str


@dataclass
class MediaRef:
    """One distinct media file referenced by a project."""

    path: str
    path_style: PathStyle
    role: Role = Role.ORIGINAL
    title: str = ""
    relative_path: str = ""
    # For an original: paths of its proxies. For a proxy: paths of the originals it stands in
    # for. Many-to-many in practice (a proxy can serve several original paths and vice versa).
    paired_paths: tuple[str, ...] = ()
    # Ids of the sequences that (transitively) use this media; empty = in project, unused.
    used_in: tuple[str, ...] = ()
    # Application cache (preview renders, media cache, conformed audio, peak files). Readers set
    # this; the planner never copies these (CLAUDE.md boundary).
    is_cache: bool = False
    # Path as saved in the project; 'offline' at save time says nothing about now.
    offline_when_saved: bool = False


@dataclass
class Project:
    source: str
    format: str
    sequences: list[Sequence] = field(default_factory=list)
    media: list[MediaRef] = field(default_factory=list)
    skipped_non_file_media: int = 0
    # Things a reader could not handle (e.g. image sequences not yet supported); shown to the user,
    # never silently dropped.
    warnings: list[str] = field(default_factory=list)

    def originals(self) -> list[MediaRef]:
        return [m for m in self.media if m.role is Role.ORIGINAL]

    def proxies(self) -> list[MediaRef]:
        return [m for m in self.media if m.role is Role.PROXY]
