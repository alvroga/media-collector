from pathlib import Path

import aaf2
import pytest

from media_collector.readers import read_project
from media_collector.writers import relink_project


def build(path: Path) -> Path:
    """Tiny AAF: composition 'Cut' uses A and B; 'Unused' is in the file but in no composition."""
    with aaf2.open(str(path), "w") as f:

        def media(name, url):
            master = f.create.MasterMob(name)
            f.content.mobs.append(master)
            src = f.create.SourceMob(name + ".src")
            f.content.mobs.append(src)
            d = f.create.ImportDescriptor()
            loc = f.create.NetworkLocator()
            loc["URLString"].value = url
            d["Locator"].append(loc)
            src.descriptor = d
            src.create_timeline_slot(25).segment = f.create.SourceClip(
                media_kind="picture", length=100
            )
            master.create_timeline_slot(25).segment = src.create_source_clip(
                slot_id=1, length=100, media_kind="picture"
            )
            return master

        a = media("A", "file:///old/a.mov")
        b = media("B", "file:///old/b%20b.mov")
        media("Unused", "file:///old/u.mov")
        comp = f.create.CompositionMob("Cut")
        f.content.mobs.append(comp)
        seq = f.create.Sequence(media_kind="picture")
        comp.create_timeline_slot(25).segment = seq
        seq.components.append(a.create_source_clip(slot_id=1, length=100, media_kind="picture"))
        seq.components.append(b.create_source_clip(slot_id=1, length=100, media_kind="picture"))
    return path


def test_read_aaf_usage(tmp_path):
    p = read_project(build(tmp_path / "s.aaf"))
    assert p.format == "aaf" and [s.name for s in p.sequences] == ["Cut"]
    assert {m.path: bool(m.used_in) for m in p.media} == {
        "/old/a.mov": True,
        "/old/b b.mov": True,
        "/old/u.mov": False,
    }
    assert not p.warnings


def test_relink_aaf(tmp_path):
    src = build(tmp_path / "s.aaf")
    before = src.read_bytes()
    out_dir = tmp_path / "out dir"
    out_dir.mkdir()
    a, b = out_dir / "a.mov", out_dir / "b b.mov"
    a.write_bytes(b"x")
    b.write_bytes(b"x")
    res = relink_project(src, out_dir / "s.aaf", {"/old/a.mov": a, "/old/b b.mov": b})
    assert (res.relinked, res.media_objects, res.left_unchanged) == (2, 3, ["/old/u.mov"])
    assert any("not been verified" in n for n in res.notes) and not res.missing_after[1:]
    p = read_project(out_dir / "s.aaf")
    by = {m.path: bool(m.used_in) for m in p.media}
    assert by[str(a)] and by[str(b)] and by["/old/u.mov"] is False  # unmapped one untouched
    assert src.read_bytes() == before  # source never modified
    with pytest.raises(FileExistsError):
        relink_project(src, out_dir / "s.aaf", {})
    assert not list(out_dir.glob("*.mc-partial"))


def test_corrupt_aaf_gives_a_clear_error(tmp_path):
    bad = tmp_path / "bad.aaf"
    bad.write_bytes(b"not an aaf")
    with pytest.raises(ValueError, match="Not a readable AAF"):
        read_project(bad)
