import json
from pathlib import Path

import pytest

from media_collector.readers import read_project
from media_collector.writers import format_like, relink_project

XML = """<?xml version="1.0" encoding="UTF-8"?>
<xmeml version="4"><sequence id="s"><name>S</name><media><video><track>
<clipitem id="c1"><file id="f1"><pathurl>file://localhost/old/a%20%26%20b.mov</pathurl></file></clipitem>
<clipitem id="c2"><file id="f1"/></clipitem>
<clipitem id="c3"><file id="f2"><pathurl>file:///old/keep.mov</pathurl></file></clipitem>
</track></video></media></sequence></xmeml>"""


def test_fcp7xml_relink(tmp_path):
    src = tmp_path / "in.xml"
    src.write_text(XML)
    new = tmp_path / "out dir" / "a & b.mov"
    new.parent.mkdir()
    new.write_bytes(b"x")
    res = relink_project(src, tmp_path / "out dir" / "in.xml", {"/old/a & b.mov": new})
    text = (tmp_path / "out dir" / "in.xml").read_text()
    assert (
        "file://localhost" + str(tmp_path).replace(" ", "%20") + "/out%20dir/a%20%26%20b.mov"
        in text
    )
    assert '<file id="f1"/>' in text  # bare reference untouched
    assert "file:///old/keep.mov" in text  # not in map: untouched
    assert (res.relinked, res.media_objects, res.left_unchanged) == (1, 2, ["/old/keep.mov"])
    assert read_project(tmp_path / "out dir" / "in.xml").format == "fcp7xml"


FCPXML = """<?xml version="1.0" encoding="UTF-8"?>
<fcpxml version="1.11"><resources>
<asset id="r1" name="A"><media-rep kind="original-media" src="file:///old/a.mov"><bookmark>AAAA</bookmark></media-rep>
<media-rep kind="proxy-media" src="file:///old/prox/a.mov"/></asset>
<asset id="r2" name="Legacy" src="file:///old/legacy%20x.mov"/>
</resources><library><event name="E"><project name="P"><sequence><spine>
<asset-clip ref="r1"/><asset-clip ref="r2"/></spine></sequence></project></event></library></fcpxml>"""


def test_fcpxml_relink_keeps_pairing_and_flags_bookmarks(tmp_path):
    src = tmp_path / "in.fcpxml"
    src.write_text(FCPXML)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    files = {}
    for old, rel in [
        ("/old/a.mov", "a.mov"),
        ("/old/prox/a.mov", "prox/a.mov"),
        ("/old/legacy x.mov", "l x.mov"),
    ]:
        f = out_dir / rel
        f.parent.mkdir(exist_ok=True)
        f.write_bytes(b"x")
        files[old] = f
    res = relink_project(src, out_dir / "in.fcpxml", files)
    assert res.relinked == 3 and not res.missing_after
    assert any("bookmark" in n for n in res.notes)
    p = read_project(out_dir / "in.fcpxml")
    by = {m.path: m for m in p.media}
    assert set(by) == {str(f) for f in files.values()}
    orig = next(m for m in p.media if m.role.value == "original" and m.path.endswith("/a.mov"))
    assert orig.paired_paths == (str(files["/old/prox/a.mov"]),)  # proxy pairing survives


def test_fcpxmld_bundle(tmp_path):
    bundle = tmp_path / "in.fcpxmld"
    bundle.mkdir()
    (bundle / "Info.fcpxml").write_text(FCPXML.replace("<bookmark>AAAA</bookmark>", ""))
    (bundle / "Extra.txt").write_text("keep me")
    new = tmp_path / "n.mov"
    new.write_bytes(b"x")
    out = tmp_path / "out.fcpxmld"
    res = relink_project(bundle, out, {"/old/a.mov": new})
    assert out.is_dir() and (out / "Extra.txt").read_text() == "keep me"
    assert res.relinked == 1 and str(new) in (out / "Info.fcpxml").read_text()
    assert (
        "/old/a.mov" in (bundle / "Info.fcpxml").read_text()
        or "file:///old/a.mov" in (bundle / "Info.fcpxml").read_text()
    )
    assert not list(out.glob("*.mc-src"))
    with pytest.raises(FileExistsError):
        relink_project(bundle, out, {})


def _otio(urls):
    clips = [
        {
            "OTIO_SCHEMA": "Clip.2",
            "name": f"c{i}",
            "media_references": {
                "DEFAULT_MEDIA": {"OTIO_SCHEMA": "ExternalReference.1", "target_url": u}
            },
        }
        for i, u in enumerate(urls)
    ]
    seq = {
        "OTIO_SCHEMA": "ImageSequenceReference.1",
        "target_url_base": "/old/seq/",
        "name_prefix": "f.",
    }
    clips.append({"OTIO_SCHEMA": "Clip.2", "name": "s", "media_references": {"DEFAULT_MEDIA": seq}})
    return json.dumps(
        {
            "OTIO_SCHEMA": "Timeline.1",
            "name": "T",
            "tracks": {
                "OTIO_SCHEMA": "Stack.1",
                "children": [{"OTIO_SCHEMA": "Track.1", "children": clips}],
            },
        },
        indent=4,
    )


def test_otio_relink_preserves_each_reference_style(tmp_path):
    src = tmp_path / "in.otio"
    (tmp_path / "rel").mkdir()
    (tmp_path / "rel/c.mov").write_bytes(b"x")
    src.write_text(_otio(['/old/a "q".mov', "file:///old/b%20b.mov", "rel/c.mov"]))
    out_dir = tmp_path / "out"
    (out_dir / "sub").mkdir(parents=True)
    new = {
        k: out_dir / "sub" / n
        for k, n in [
            ('/old/a "q".mov', "a.mov"),
            ("/old/b b.mov", "b b.mov"),
            (str((tmp_path / "rel/c.mov").resolve()), "c.mov"),
        ]
    }
    for f in new.values():
        f.write_bytes(b"x")
    res = relink_project(src, out_dir / "in.otio", new)
    d = json.loads((out_dir / "in.otio").read_text())
    urls = [
        c["media_references"]["DEFAULT_MEDIA"].get("target_url")
        for c in d["tracks"]["children"][0]["children"]
    ]
    assert urls[0] == str(out_dir / "sub/a.mov")  # plain absolute stays plain
    assert (
        urls[1] == "file://" + str(out_dir / "sub").replace(" ", "%20") + "/b%20b.mov"
    )  # URL stays URL
    assert urls[2] == "sub/c.mov"  # relative stays relative (to the new location)
    assert (
        d["tracks"]["children"][0]["children"][3]["media_references"]["DEFAULT_MEDIA"][
            "target_url_base"
        ]
        == "/old/seq/"
    )
    assert res.relinked == 3 and not res.missing_after


def test_refuses_overwrite_same_file_and_unknown_format(tmp_path):
    src = tmp_path / "in.otio"
    src.write_text(_otio(["/old/a.mov"]))
    with pytest.raises(ValueError):
        relink_project(src, src, {})
    (tmp_path / "exists.otio").write_text("keep")
    with pytest.raises(FileExistsError):
        relink_project(src, tmp_path / "exists.otio", {})
    assert (tmp_path / "exists.otio").read_text() == "keep"
    (tmp_path / "x.edl").write_bytes(b"")
    with pytest.raises(ValueError):
        relink_project(tmp_path / "x.edl", tmp_path / "y.edl", {})


def test_relinked_name():
    from media_collector.writers import relinked_name

    assert relinked_name("Show.prproj") == "Show_relinked.prproj"
    assert relinked_name("Cut.fcpxmld") == "Cut_relinked.fcpxmld"


def test_format_like():
    out = Path("/out")
    assert format_like("file:///o/a.mov", Path("/n/a b.mov"), out) == "file:///n/a%20b.mov"
    assert (
        format_like("file://localhost/o/a.mov", Path("/n/a.mov"), out) == "file://localhost/n/a.mov"
    )
    assert format_like("/o/a.mov", Path("/n/a.mov"), out) == "/n/a.mov"
    assert format_like("rel/a.mov", Path("/out/x/a.mov"), out) == "x/a.mov"


FCPXML_BM = """<?xml version="1.0" encoding="UTF-8"?>
<fcpxml version="1.14"><resources>
<asset id="r1" name="A">
    <media-rep kind="original-media" src="file:///old/a.mov">
        <bookmark>AAAA1111</bookmark>
    </media-rep>
    <media-rep kind="proxy-media" src="file:///old/prox/a.mov">
        <bookmark>BBBB2222</bookmark>
    </media-rep>
</asset>
<asset id="r2" name="Keep"><media-rep kind="original-media" src="file:///old/keep.mov">
    <bookmark>CCCC3333</bookmark></media-rep></asset>
</resources><library><event name="E"><project name="P"><sequence><spine>
<asset-clip ref="r1"/><asset-clip ref="r2"/></spine></sequence></project></event></library></fcpxml>"""


def test_fcpxml_drops_stale_bookmarks_only_on_relinked_entries(tmp_path):
    src = tmp_path / "in.fcpxml"
    src.write_text(FCPXML_BM)
    out = tmp_path / "out"
    out.mkdir()
    a, p = out / "a.mov", out / "prox_a.mov"
    a.write_bytes(b"x")
    p.write_bytes(b"x")
    res = relink_project(src, out / "in.fcpxml", {"/old/a.mov": a, "/old/prox/a.mov": p})
    text = (out / "in.fcpxml").read_text()
    assert "AAAA1111" not in text and "BBBB2222" not in text  # relinked -> stale bookmarks gone
    assert "CCCC3333" in text  # not relinked -> untouched
    assert "file:///old/keep.mov" in text
    assert any("Removed 2 stale media bookmark" in n for n in res.notes)
    back = read_project(out / "in.fcpxml")
    assert {m.path for m in back.media if m.role.value == "proxy"} == {
        str(p)
    }  # still valid, pairing kept
    assert text.count("<media-rep") == 3 and text.count("</media-rep>") == 3


def test_failed_bundle_relink_leaves_nothing_behind(tmp_path, monkeypatch):
    import media_collector.writers.fcpxml as w

    bundle = tmp_path / "in.fcpxmld"
    bundle.mkdir()
    (bundle / "Info.fcpxml").write_text(FCPXML.replace("<bookmark>AAAA</bookmark>", ""))
    out = tmp_path / "out.fcpxmld"
    monkeypatch.setattr(w, "rewrite_text_file", lambda *a: (_ for _ in ()).throw(OSError("x")))
    with pytest.raises(OSError):
        relink_project(bundle, out, {})
    assert not out.exists()
    monkeypatch.undo()
    assert relink_project(bundle, out, {}).output == out  # retry works


def test_verify_failure_keeps_output_and_adds_a_note(tmp_path, monkeypatch):
    from media_collector import readers

    src = tmp_path / "in.xml"
    src.write_text(XML)
    out = tmp_path / "out.xml"
    monkeypatch.setattr(readers, "read_project", lambda p: (_ for _ in ()).throw(ValueError("bad")))
    res = relink_project(src, out, {})
    assert out.exists() and any("could not be re-read" in n for n in res.notes)


def test_aep_unreadable_record_is_reported(tmp_path):
    from media_collector.readers.aep import read_aep

    f = tmp_path / "x.aep"
    f.write_bytes(
        b'RIFX\x00\x00\x00\x00{"ascendcount_base":1,"fullpath":"/m/a.mov"}'
        b'{"ascendcount_base":1,"fullpath":"\xff\xfe"}'
    )
    p = read_aep(f)
    assert [m.path for m in p.media] == ["/m/a.mov"]
    assert any("1 footage record" in w for w in p.warnings)
