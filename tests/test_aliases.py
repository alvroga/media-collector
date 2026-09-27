import gzip
import os
from pathlib import Path

import pytest

from media_collector import paths
from media_collector.model import MediaRef, PathStyle
from media_collector.paths import (
    _compute_alias_names,
    canonical_posix,
    path_from_reference,
    resolve_source,
)
from media_collector.readers import read_project
from media_collector.writers import relink_project


@pytest.fixture
def boot_named_macintosh_hd(monkeypatch):
    monkeypatch.setattr(
        paths, "_alias_names", lambda: frozenset({"macintosh hd", "macintosh hd - data"})
    )


def test_canonical_posix(boot_named_macintosh_hd):
    assert canonical_posix("/Volumes/Macintosh HD/Users/x/a.mov") == "/Users/x/a.mov"
    assert (
        canonical_posix("/Volumes/macintosh hd - data/Users/x/a.mov") == "/Users/x/a.mov"
    )  # case-insensitive
    assert canonical_posix("/Volumes/Macintosh HD") == "/"
    assert canonical_posix("/System/Volumes/Data/Users/x/a.mov") == "/Users/x/a.mov"
    assert canonical_posix("/Users/x/a.mov") == "/Users/x/a.mov"
    assert canonical_posix("/Volumes/Media/a.mov") == "/Volumes/Media/a.mov"  # a real other volume
    assert canonical_posix("/Volumes/Macintosh HD2/a.mov") == "/Volumes/Macintosh HD2/a.mov"


def test_alias_names_come_from_what_is_mounted(tmp_path):
    vols = tmp_path / "Volumes"
    vols.mkdir()
    os.symlink("/", vols / "MacSSD")  # this Mac's boot volume, custom name
    (vols / "Macintosh HD").mkdir()  # a REAL other drive that happens to use Apple's default name
    (vols / "Media").mkdir()
    names = _compute_alias_names(vols)
    assert "macssd" in names
    assert "macintosh hd" not in names  # mounted here and not the boot volume: not an alias
    assert "media" not in names
    assert (
        "macintosh hd - data" in names
    )  # not mounted here: default alias (project from another Mac)
    assert "macintosh hd" in _compute_alias_names(tmp_path / "missing")  # no /Volumes at all


def test_windows_paths_untouched(boot_named_macintosh_hd):
    assert path_from_reference(r"C:\Volumes\Macintosh HD\a.mov") == (
        r"C:\Volumes\Macintosh HD\a.mov",
        PathStyle.WINDOWS,
    )
    assert path_from_reference("file:///Volumes/Macintosh%20HD/Users/x/a.mov") == (
        "/Users/x/a.mov",
        PathStyle.POSIX,
    )


def test_resolve_source_and_mapping_keys_accept_any_spelling(boot_named_macintosh_hd, tmp_path):
    m = MediaRef(path="/Volumes/Macintosh HD/Users/demo/Movies/L/a.mov", path_style=PathStyle.POSIX)
    assert resolve_source(m, {}) == Path("/Users/demo/Movies/L/a.mov")
    assert resolve_source(m, {"/Users/demo/Movies/L": str(tmp_path)}) == tmp_path / "a.mov"
    assert (
        resolve_source(m, {"/Volumes/Macintosh HD/Users/demo/Movies/L": str(tmp_path)})
        == tmp_path / "a.mov"
    )


FCPXML = """<?xml version="1.0" encoding="UTF-8"?>
<fcpxml version="1.11"><resources>
<asset id="r1" name="A"><media-rep kind="original-media" src="file:///Volumes/Macintosh%20HD/Users/x/a.mov"/></asset>
<asset id="r2" name="A again"><media-rep kind="original-media" src="file:///Users/x/a.mov"/></asset>
</resources><library><event name="E"><project name="P" uid="P1"><sequence><spine>
<asset-clip ref="r1"/><asset-clip ref="r2"/></spine></sequence></project></event></library></fcpxml>"""


def test_same_file_in_two_spellings_is_one_file(boot_named_macintosh_hd, tmp_path):
    f = tmp_path / "p.fcpxml"
    f.write_text(FCPXML)
    p = read_project(f)
    assert [m.path for m in p.media] == ["/Users/x/a.mov"]
    assert p.media[0].used_in == ("P1",)
    # relinking rewrites BOTH spellings from the single canonical map key
    new = tmp_path / "new" / "a.mov"
    new.parent.mkdir()
    new.write_bytes(b"x")
    res = relink_project(f, tmp_path / "new" / "p.fcpxml", {"/Users/x/a.mov": new})
    assert res.relinked == 2 and not res.left_unchanged
    text = (tmp_path / "new" / "p.fcpxml").read_text()
    assert "Macintosh" not in text and "/Users/x/" not in text


PRPROJ = """<?xml version="1.0" encoding="UTF-8" ?>
<PremiereData Version="3">
\t<Project ObjectRef="1"/>
\t<Sequence ObjectUID="seq-1" ClassID="c" Version="1">
\t\t<Name>S</Name>
\t\t<Link ObjectURef="m1"/>
\t</Sequence>
\t<Media ObjectUID="m1" ClassID="c" Version="30">
\t\t<RelativePath>./a.mov</RelativePath>
\t\t<ActualMediaFilePath>/Volumes/Macintosh HD/Users/x/a.mov</ActualMediaFilePath>
\t\t<FilePath>/Volumes/Macintosh HD/Users/x/a.mov</FilePath>
\t</Media>
</PremiereData>
"""


def test_premiere_reader_and_writer_agree_on_the_canonical_spelling(
    boot_named_macintosh_hd, tmp_path
):
    src = tmp_path / "in.prproj"
    with gzip.open(src, "wt") as f:
        f.write(PRPROJ)
    p = read_project(src)
    assert [m.path for m in p.media] == ["/Users/x/a.mov"]
    new = tmp_path / "out" / "a.mov"
    new.parent.mkdir()
    new.write_bytes(b"x")
    res = relink_project(src, tmp_path / "out" / "in.prproj", {"/Users/x/a.mov": new})
    assert res.relinked == 1 and not res.left_unchanged and not res.missing_after
    assert [m.path for m in read_project(tmp_path / "out" / "in.prproj").media] == [str(new)]
