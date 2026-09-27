"""Filesystem helpers. The macOS-specific call lives here (ADR-0004)."""

from __future__ import annotations

import ctypes
import ctypes.util
import errno
import os
from collections.abc import Callable
from pathlib import Path

_RENAME_EXCL = 0x4  # renamex_np flag: fail with EEXIST instead of replacing
_UNSUPPORTED = {errno.ENOTSUP, errno.EINVAL, errno.ENOSYS}


def _renamex_np():
    try:
        fn = ctypes.CDLL(ctypes.util.find_library("c") or "libc.dylib", use_errno=True).renamex_np
    except (OSError, AttributeError):
        return None
    fn.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
    fn.restype = ctypes.c_int
    return fn


_RENAME = _renamex_np()


def move_no_clobber(src: Path, dst: Path) -> None:
    """Move `src` to `dst`, raising FileExistsError instead of ever replacing `dst`.

    Uses the kernel's exclusive rename (atomic, no race) where the filesystem supports it (APFS,
    HFS+); on others (exFAT, SMB, ...) falls back to a check followed by `os.replace`, which
    leaves a very small window."""
    if _RENAME is not None:
        if _RENAME(os.fsencode(src), os.fsencode(dst), _RENAME_EXCL) == 0:
            return
        err = ctypes.get_errno()
        if err == errno.EEXIST:
            raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), str(dst))
        if err not in _UNSUPPORTED:
            raise OSError(err, os.strerror(err), str(dst))
    if Path(dst).exists():
        raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), str(dst))
    os.replace(src, dst)


def numbered_name(name: str, n: int) -> str:
    """`Show.prproj` -> `Show.prproj` (n=0), `Show_1.prproj`, `Show_2.prproj`, ..."""
    if n == 0:
        return name
    p = Path(name)
    return f"{p.stem}_{n}{p.suffix}"


def next_version(directory: Path, name: str, relinked: Callable[[str], str]) -> int:
    """The first version number n for which neither `name` nor its relinked twin exists in `directory`
    (n=0: the plain names; n=1: `Show_1.prproj` and `Show_1_relinked.prproj`; ...). Original and
    relinked project of one run share a number, so the pair always stays matched."""
    n = 0
    while any(
        (directory / x).exists() for x in (numbered_name(name, n), relinked(numbered_name(name, n)))
    ):
        n += 1
    return n
