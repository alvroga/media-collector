from pathlib import Path

import pytest

from media_collector.model import PathStyle, Role
from media_collector.readers.premiere import is_premiere_cache, read_premiere

ASSETS = Path(__file__).parent.parent / "assets"
SIMPLE = ASSETS / "296800_1.prproj"
COMPLEX = ASSETS / "4573100_26CES_VR_Bring-Up_1.prproj"

needs_simple = pytest.mark.skipif(not SIMPLE.exists(), reason="sample project not present")
needs_complex = pytest.mark.skipif(not COMPLEX.exists(), reason="sample project not present")


@needs_simple
def test_simple_project():
    p = read_premiere(SIMPLE)
    assert p.format == "premiere"
    assert len(p.sequences) == 2
    assert p.media, "no media found"
    assert all(m.path_style is PathStyle.POSIX for m in p.media)
    mov = next(m for m in p.media if m.path.endswith("/Movies/06b25b4d-000014-1.mov"))
    seq = next(x for x in p.sequences if x.name == "06b25b4d-000014-1")
    assert mov.used_in == (seq.id,)
    assert mov.role is Role.ORIGINAL
    assert len({m.path for m in p.media}) == len(p.media)  # deduplicated by path


@pytest.mark.slow
@needs_complex
def test_complex_project():
    p = read_premiere(COMPLEX)
    assert len(p.sequences) == 222
    assert len({s.id for s in p.sequences}) == 222  # ids unique even where names collide
    assert len({s.name for s in p.sequences}) < 222
    assert any(m.path_style is PathStyle.WINDOWS for m in p.media)
    assert p.skipped_non_file_media > 0  # e.g. SyntheticTranscript
    assert all(m.path[0] != "1" or not m.path.isdigit() for m in p.media)
    proxies = p.proxies()
    assert proxies
    by_path = {m.path: m for m in p.media}
    for px in proxies:
        for orig in px.paired_paths:
            assert by_path[orig].role is Role.ORIGINAL
            assert px.path in by_path[orig].paired_paths
    assert sum(1 for m in p.originals() if m.paired_paths) > 700


def test_cache_detection():
    yes = [
        r"Q:\P\Adobe Premiere Pro Video Previews\X.PRV\Rendered - a.mov",
        r"C:\Users\u\Library\Adobe Premiere Pro Audio Previews\a.pfa",
        "/Users/u/Library/Application Support/Adobe/Common/Media Cache Files/a.cfa",
        "/Users/u/Movies/x.PRV/clip.mov",
        "/a/b/clip.pek",
    ]
    no = [
        "/Volumes/D/Shoot/A001/clip.mov",
        r"O:\Media\Previews Reference\a.mov",
        "/a/Cache Money/x.mov",
    ]
    assert all(is_premiere_cache(p) for p in yes)
    assert not any(is_premiere_cache(p) for p in no)


@pytest.mark.slow
@needs_complex
def test_complex_cache_flagged_and_excluded():
    from media_collector.plan import PlanOptions, build_plan

    p = read_premiere(COMPLEX)
    cache = [m for m in p.media if m.is_cache]
    assert len(cache) > 400
    assert all("Video Previews" in m.path or ".PRV" in m.path for m in cache)
    plan = build_plan(p, PlanOptions())
    assert not any(c.source.is_cache for c in plan.copies)
