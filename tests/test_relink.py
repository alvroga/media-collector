import gzip
from pathlib import Path

import pytest

from media_collector.readers.premiere import read_premiere
from media_collector.writers.premiere import relink_premiere

XML = """<?xml version="1.0" encoding="UTF-8" ?>
<PremiereData Version="3">
\t<Project ObjectRef="1"/>
\t<Project ObjectID="1" ClassID="x" Version="45">
\t\t<Properties>
\t\t\t<project.settings.lastknowngoodprojectpath>{old_proj}</project.settings.lastknowngoodprojectpath>
\t\t</Properties>
\t</Project>
\t<Media ObjectUID="m1" ClassID="c" Version="30">
\t\t<RelativePath>./a &amp; b.mov</RelativePath>
\t\t<ActualMediaFilePath>{old}/a &amp; b.mov</ActualMediaFilePath>
\t\t<FilePath>{old}/a &amp; b.mov</FilePath>
\t\t<Title>a &amp; b.mov</Title>
\t\t<MediaFileHistory0>{old}/a &amp; b.mov</MediaFileHistory0>
\t</Media>
\t<Media ObjectUID="m2" ClassID="c" Version="30">
\t\t<ActualMediaFilePath>{old}/other.mov</ActualMediaFilePath>
\t\t<FilePath>{old}/other.mov</FilePath>
\t\t<Title>other.mov</Title>
\t</Media>
</PremiereData>
"""


def read_text(p):
    with gzip.open(p, "rt") as f:
        return f.read()


def make(tmp_path):
    old = tmp_path / "old"
    new = tmp_path / "new"
    old.mkdir(), new.mkdir()
    (new / "sub").mkdir()
    (new / "sub/a & b.mov").write_bytes(b"x")
    src = tmp_path / "in.prproj"
    with gzip.open(src, "wb") as f:
        f.write(XML.format(old=old, old_proj=old / "in.prproj").encode())
    return src, old, new


def test_relink_rewrites_only_path_fields(tmp_path):
    src, old, new = make(tmp_path)
    out = new / "out.prproj"
    res = relink_premiere(src, out, {f"{old}/a & b.mov": new / "sub/a & b.mov"})
    text = read_text(out)
    assert f"<FilePath>{new}/sub/a &amp; b.mov</FilePath>" in text
    assert f"<ActualMediaFilePath>{new}/sub/a &amp; b.mov</ActualMediaFilePath>" in text
    assert f"<MediaFileHistory0>{new}/sub/a &amp; b.mov</MediaFileHistory0>" in text
    assert "<RelativePath>./sub/a &amp; b.mov</RelativePath>" in text
    assert f"<project.settings.lastknowngoodprojectpath>{out}<" in text
    assert f"{old}/other.mov" in text  # not in map: untouched
    assert res.relinked == 1 and res.media_objects == 2
    assert res.left_unchanged == [f"{old}/other.mov"]
    # everything except the changed lines is identical
    a = read_text(src).splitlines()
    b = text.splitlines()
    assert len(a) == len(b)
    assert sum(x != y for x, y in zip(a, b)) == 5  # 4 media fields + project path
    assert Path(res.missing_after[0]).name == "other.mov"  # verification flags the old, absent path


def test_refuses_overwrite_and_leaves_source_intact(tmp_path):
    src, _old, new = make(tmp_path)
    before = src.read_bytes()
    out = new / "out.prproj"
    out.write_bytes(b"existing")
    with pytest.raises(FileExistsError):
        relink_premiere(src, out, {})
    with pytest.raises(ValueError):
        relink_premiere(src, src, {})
    assert out.read_bytes() == b"existing" and src.read_bytes() == before


def test_relink_result_readable_by_reader(tmp_path):
    src, old, new = make(tmp_path)
    out = new / "out.prproj"
    relink_premiere(src, out, {f"{old}/a & b.mov": new / "sub/a & b.mov"})
    paths = {m.path for m in read_premiere(out).media}
    assert str(new / "sub/a & b.mov") in paths


def test_failed_relink_leaves_no_partial_and_can_be_retried(tmp_path, monkeypatch):
    import media_collector.writers.premiere as w

    src, _old, new = make(tmp_path)
    out = new / "out.prproj"

    def boom(*a):
        raise OSError("disk went away")

    monkeypatch.setattr(w, "move_no_clobber", boom)
    with pytest.raises(OSError):
        relink_premiere(src, out, {})
    assert not out.exists() and not list(new.glob("*.mc-partial"))
    monkeypatch.undo()
    relink_premiere(src, out, {})  # the retry is not blocked
    assert out.exists()


def test_relink_never_replaces_a_file_that_appeared_meanwhile(tmp_path, monkeypatch):
    import media_collector.writers.premiere as w

    src, _old, new = make(tmp_path)
    out = new / "out.prproj"
    real = w.move_no_clobber

    def racing(a, b):
        b.write_bytes(b"someone else")
        real(a, b)

    monkeypatch.setattr(w, "move_no_clobber", racing)
    with pytest.raises(FileExistsError):
        relink_premiere(src, out, {})
    assert out.read_bytes() == b"someone else" and not list(new.glob("*.mc-partial"))
