import json
from pathlib import Path

import pytest

from media_collector.model import PathStyle, Role
from media_collector.paths import path_from_reference
from media_collector.readers import read_project

AIRPLANES = Path.home() / "Documents" / "UMM Airplanes"


def test_path_from_reference():
    assert path_from_reference("file:///Volumes/My%20Disk/a%20b.mov") == (
        "/Volumes/My Disk/a b.mov",
        PathStyle.POSIX,
    )
    assert path_from_reference("file://localhost/Users/x/a.mov") == (
        "/Users/x/a.mov",
        PathStyle.POSIX,
    )
    assert path_from_reference("file:///C:/Media/a%20b.mov") == (
        "C:\\Media\\a b.mov",
        PathStyle.WINDOWS,
    )
    assert path_from_reference("file://nas/share/Media/a.mov") == (
        "\\\\nas\\share\\Media\\a.mov",
        PathStyle.WINDOWS,
    )
    assert path_from_reference(r"O:\Media\a.mov") == (r"O:\Media\a.mov", PathStyle.WINDOWS)
    assert path_from_reference("/a/b.mov") == ("/a/b.mov", PathStyle.POSIX)
    assert path_from_reference("https://example.com/a.mov") is None
    assert path_from_reference("1398035014") is None
    assert path_from_reference("") is None
    assert path_from_reference("rel/a.mov", Path("/base")) == ("/base/rel/a.mov", PathStyle.POSIX)
    assert path_from_reference("rel/a.mov") is None


FCP7 = """<?xml version="1.0" encoding="UTF-8"?>
<xmeml version="4">
  <project><children>
    <clip id="masterclip-9"><file id="file-9"><pathurl>file:///m/unused.mov</pathurl></file></clip>
  </children></project>
  <sequence id="seq-A"><name>Main</name><media><video><track>
    <clipitem id="c1"><file id="file-1"><pathurl>file:///m/a%20one.mov</pathurl></file></clipitem>
    <clipitem id="c2"><file id="file-2"><pathurl>file:///C:/win/b.mov</pathurl></file></clipitem>
    <clipitem id="c3"><sequence id="seq-N"><name>Nested</name><media><video><track>
      <clipitem id="c4"><file id="file-3"><pathurl>file:///m/nested.mov</pathurl></file></clipitem>
    </track></video></media></sequence></clipitem>
  </track></video></media></sequence>
  <sequence id="seq-B"><name>Second</name><media><video><track>
    <clipitem id="c5"><file id="file-1"/></clipitem>
  </track></video></media></sequence>
</xmeml>"""


def test_fcp7xml(tmp_path):
    f = tmp_path / "p.xml"
    f.write_text(FCP7)
    p = read_project(f)
    assert p.format == "fcp7xml"
    assert [(s.id, s.name) for s in p.sequences] == [
        ("seq-A", "Main"),
        ("seq-B", "Second"),
    ]  # nested not separate
    by = {m.path: m for m in p.media}
    assert by["/m/a one.mov"].used_in == ("seq-A", "seq-B")  # bare <file id/> reference resolved
    assert by["/m/nested.mov"].used_in == ("seq-A",)  # nested sequence counts for its parent
    assert by["C:\\win\\b.mov"].path_style is PathStyle.WINDOWS
    assert by["/m/unused.mov"].used_in == ()  # bin-only


FCPXML = """<?xml version="1.0" encoding="UTF-8"?>
<fcpxml version="1.11">
  <resources>
    <asset id="r1" name="A"><media-rep kind="original-media" src="file:///m/a.mov"/>
      <media-rep kind="proxy-media" src="file:///p/a_proxy.mov"/></asset>
    <asset id="r2" name="B"><media-rep kind="original-media" src="file:///m/b.mov"/></asset>
    <asset id="r3" name="Old" src="file:///m/legacy.mov"/>
    <asset id="r4" name="Unused"><media-rep kind="original-media" src="file:///m/unused.mov"/></asset>
    <media id="r5" name="Compound"><sequence><spine><asset-clip ref="r2" name="B"/></spine></sequence></media>
  </resources>
  <library><event name="E">
    <project name="Cut 1" uid="P1"><sequence><spine>
      <asset-clip ref="r1" name="A"/><ref-clip ref="r5" name="Compound"/>
    </spine></sequence></project>
    <project name="Cut 2" uid="P2"><sequence><spine><asset-clip ref="r3" name="Old"/></spine></sequence></project>
  </event></library>
</fcpxml>"""


def test_fcpxml_proxies_compound_and_projects(tmp_path):
    f = tmp_path / "p.fcpxml"
    f.write_text(FCPXML)
    p = read_project(f)
    assert [(s.id, s.name) for s in p.sequences] == [("P1", "Cut 1"), ("P2", "Cut 2")]
    by = {m.path: m for m in p.media}
    assert by["/m/a.mov"].used_in == ("P1",) and by["/m/a.mov"].paired_paths == ("/p/a_proxy.mov",)
    assert by["/p/a_proxy.mov"].role is Role.PROXY and by["/p/a_proxy.mov"].paired_paths == (
        "/m/a.mov",
    )
    assert by["/m/b.mov"].used_in == ("P1",)  # reached through the compound clip
    assert by["/m/legacy.mov"].used_in == ("P2",)  # legacy asset/@src
    assert by["/m/unused.mov"].used_in == ()


def test_fcpxmld_bundle_and_xml_sniffing(tmp_path):
    bundle = tmp_path / "x.fcpxmld"
    bundle.mkdir()
    (bundle / "Info.fcpxml").write_text(FCPXML)
    assert read_project(bundle).format == "fcpxml"
    (tmp_path / "a.xml").write_text(FCPXML)
    (tmp_path / "b.xml").write_text(FCP7)
    assert read_project(tmp_path / "a.xml").format == "fcpxml"
    assert read_project(tmp_path / "b.xml").format == "fcp7xml"
    (tmp_path / "c.xml").write_text("<foo/>")
    with pytest.raises(ValueError):
        read_project(tmp_path / "c.xml")


def _clip(name, refs, active=None):
    return {
        "OTIO_SCHEMA": "Clip.2",
        "name": name,
        "media_references": refs,
        "active_media_reference_key": active or next(iter(refs)),
    }


def _ext(url):
    return {"OTIO_SCHEMA": "ExternalReference.1", "target_url": url}


def test_otio_multiple_references_images_and_relative(tmp_path):
    seq = {"OTIO_SCHEMA": "ImageSequenceReference.1", "target_url_base": "/x/", "name_prefix": "f."}
    tl = {
        "OTIO_SCHEMA": "Timeline.1",
        "name": "TL",
        "tracks": {
            "OTIO_SCHEMA": "Stack.1",
            "children": [
                {
                    "OTIO_SCHEMA": "Track.1",
                    "children": [
                        _clip(
                            "a", {"Full": _ext("/m/full.mov"), "Proxy": _ext("/m/prx.mp4")}, "Proxy"
                        ),
                        _clip("b", {"DEFAULT_MEDIA": _ext("file:///m/b%20b.mov")}),
                        _clip("c", {"DEFAULT_MEDIA": _ext("rel/c.mov")}),
                        _clip("d", {"DEFAULT_MEDIA": seq}),
                        _clip("e", {"DEFAULT_MEDIA": _ext("https://example.com/e.mov")}),
                    ],
                }
            ],
        },
    }
    f = tmp_path / "t.otio"
    f.write_text(json.dumps(tl))
    p = read_project(f)
    by = {m.path: m for m in p.media}
    assert by["/m/full.mov"].role is Role.ORIGINAL and by["/m/full.mov"].paired_paths == (
        "/m/prx.mp4",
    )
    assert by["/m/prx.mp4"].role is Role.PROXY and by["/m/prx.mp4"].paired_paths == ("/m/full.mov",)
    assert "/m/b b.mov" in by
    assert str((tmp_path / "rel/c.mov").resolve()) in by  # relative to the .otio
    assert p.skipped_non_file_media == 1  # the https reference
    assert len(p.warnings) == 1 and "image-sequence" in p.warnings[0]
    assert all(m.used_in == ("timeline-1",) for m in p.media)


def test_otio_collection_gives_one_sequence_per_timeline(tmp_path):
    def tl(n, url):
        return {
            "OTIO_SCHEMA": "Timeline.1",
            "name": n,
            "tracks": {
                "OTIO_SCHEMA": "Stack.1",
                "children": [
                    {"OTIO_SCHEMA": "Track.1", "children": [_clip(n, {"DEFAULT_MEDIA": _ext(url)})]}
                ],
            },
        }

    f = tmp_path / "c.otio"
    f.write_text(
        json.dumps(
            {
                "OTIO_SCHEMA": "SerializableCollection.1",
                "children": [tl("One", "/m/1.mov"), tl("Two", "/m/2.mov")],
            }
        )
    )
    p = read_project(f)
    assert [s.name for s in p.sequences] == ["One", "Two"]
    assert {m.path: m.used_in for m in p.media} == {
        "/m/1.mov": ("timeline-1",),
        "/m/2.mov": ("timeline-2",),
    }


@pytest.mark.skipif(not AIRPLANES.exists(), reason="Airplanes fixture not present")
def test_all_formats_agree_on_the_airplanes_fixture():
    files = [
        "Airplanes - 01 Trailer.prproj",
        "Airplanes - 01 Trailer.xml",
        "Airplanes - 01 Trailer.fcpxmld",
        "Airplanes - 01 Trailer.otio",
    ]
    sets = {f: {m.path for m in read_project(AIRPLANES / f).originals()} for f in files}
    assert len(sets[files[0]]) == 14
    assert all(s == sets[files[0]] for s in sets.values())


def test_aep_reader_finds_footage_records(tmp_path):
    def rec(p, folder="false"):
        return (
            f'{{"ascendcount_base":1,"ascendcount_target":3,"fullpath":"{p}","platform":2,'
            f'"server_name":"","server_volume_name":"","target_is_folder":{folder}}}'
        ).encode()

    blob = (
        b"RIFX\x00\x00\x01\x00Egg!svap"
        + b"\x00" * 9
        + rec("/m/a.mov")
        + b"opti"
        + b"\x01\x02"
        + rec("/m/a.mov")
        + rec("/m/Sub Folder", "true")
        + rec("C:\\\\media\\\\w.mov")
        + rec("1234")
        + b"junk{not json}"
    )
    f = tmp_path / "x.aep"
    f.write_bytes(blob)
    p = read_project(f)
    assert p.format == "aep" and p.sequences == []  # no real sequences: Scope makes no sense
    assert {m.path: m.path_style.value for m in p.media} == {
        "/m/a.mov": "posix",
        "C:\\media\\w.mov": "windows",
    }
    assert all(m.used_in == ("project",) for m in p.media)  # no per-composition usage yet
    assert p.skipped_non_file_media == 1 and p.warnings == []
    (tmp_path / "bad.aep").write_bytes(b"not aep")
    with pytest.raises(ValueError, match="RIFX"):
        read_project(tmp_path / "bad.aep")


@pytest.mark.skipif(
    not AIRPLANES.exists() or not (AIRPLANES / "Airplanes.aep").exists(), reason="fixture missing"
)
def test_aep_fixture():
    p = read_project(AIRPLANES / "Airplanes.aep")
    assert len(p.media) == 10 and all(m.path.endswith(".mov") for m in p.media)


def test_bundle_and_info_fcpxml_are_the_same_project(tmp_path):
    from media_collector.readers import normalize_project_path

    bundle = tmp_path / "x.fcpxmld"
    bundle.mkdir()
    (bundle / "Info.fcpxml").write_text(FCPXML)
    assert normalize_project_path(bundle / "Info.fcpxml") == bundle
    assert read_project(bundle / "Info.fcpxml").format == "fcpxml"
    assert (
        normalize_project_path(tmp_path / "Info.fcpxml") == tmp_path / "Info.fcpxml"
    )  # not in a bundle


@pytest.mark.parametrize(
    "name,hint",
    [
        ("L.fcpbundle", "Export XML"),
        ("p.drp", "Resolve"),
        ("p.drt", "Resolve"),
        ("c.edl", "no file locations"),
    ],
)
def test_helpful_messages_for_unsupported_projects(tmp_path, name, hint):
    f = tmp_path / name
    f.mkdir() if name.endswith(".fcpbundle") else f.write_bytes(b"")
    with pytest.raises(ValueError, match=hint):
        read_project(f)
