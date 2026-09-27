import hashlib
import os
from pathlib import Path

from media_collector.copier import PARTIAL_SUFFIX, Status, execute
from media_collector.model import MediaRef, PathStyle, Project
from media_collector.paths import resolve_source
from media_collector.plan import PlanOptions, build_plan


def make(tmp_path, files):
    src = tmp_path / "src"
    refs = []
    for rel, data in files.items():
        f = src / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(data)
        refs.append(MediaRef(path=str(f), path_style=PathStyle.POSIX, used_in=("S",)))
    return Project(source="p", format="t", media=refs), src


def levels(tmp_path):  # number of folder levels in tmp_path, so tests can keep 'src/...'
    return len([p for p in tmp_path.parts if p != "/"])


def opts(tmp_path):
    return PlanOptions(preserve_after_levels=levels(tmp_path))


def test_copy_verify_and_structure(tmp_path):
    proj, _ = make(tmp_path, {"A/one.mov": b"1" * 100, "B/C/two.mov": b"2" * 50})
    dest = tmp_path / "out"
    rep = execute(build_plan(proj, opts(tmp_path)), dest)
    assert rep.ok and rep.count(Status.COPIED) == 2
    assert (dest / "src/A/one.mov").read_bytes() == b"1" * 100
    assert (dest / "src/B/C/two.mov").read_bytes() == b"2" * 50
    r = next(x for x in rep.results if x.media.path.endswith("one.mov"))
    assert r.sha256 == hashlib.sha256(b"1" * 100).hexdigest()
    assert not list(dest.rglob(f"*{PARTIAL_SUFFIX}"))
    assert set(rep.path_map()) == {m.path for m in proj.media}


def test_rerun_skips_identical_and_never_overwrites(tmp_path):
    proj, _ = make(tmp_path, {"a.mov": b"x" * 10})
    dest = tmp_path / "out"
    plan = build_plan(proj, opts(tmp_path))
    execute(plan, dest)
    again = execute(plan, dest)
    assert again.count(Status.SKIPPED_IDENTICAL) == 1
    target = dest / "src/a.mov"
    target.write_bytes(b"DIFFERENT")
    conflict = execute(plan, dest)
    assert conflict.count(Status.CONFLICT) == 1 and not conflict.ok
    assert target.read_bytes() == b"DIFFERENT"  # untouched


def test_dry_run_writes_nothing(tmp_path):
    proj, _ = make(tmp_path, {"a.mov": b"x" * 10})
    dest = tmp_path / "out"
    rep = execute(build_plan(proj, opts(tmp_path)), dest, dry_run=True)
    assert rep.count(Status.WOULD_COPY) == 1 and rep.total_bytes == 10
    assert not dest.exists()


def test_missing_and_unmapped_reported_not_fatal(tmp_path):
    proj, _ = make(tmp_path, {"a.mov": b"x"})
    proj.media.append(MediaRef(path="/nope/gone.mov", path_style=PathStyle.POSIX, used_in=("S",)))
    proj.media.append(
        MediaRef(path=r"O:\Media\w.mov", path_style=PathStyle.WINDOWS, used_in=("S",))
    )
    rep = execute(build_plan(proj, opts(tmp_path)), tmp_path / "out")
    assert rep.count(Status.COPIED) == 1 and rep.count(Status.MISSING) == 2 and not rep.ok


def test_source_never_modified(tmp_path):
    proj, src = make(tmp_path, {"a.mov": b"abc"})
    before = (src / "a.mov").stat()
    execute(build_plan(proj, opts(tmp_path)), tmp_path / "out")
    after = (src / "a.mov").stat()
    assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
    assert (src / "a.mov").read_bytes() == b"abc"


def test_windows_mapping(tmp_path):
    vol = tmp_path / "Media"
    (vol / "Shoot").mkdir(parents=True)
    (vol / "Shoot/a.mov").write_bytes(b"w")
    m = MediaRef(path=r"\\?\O:\Shoot\a.mov", path_style=PathStyle.WINDOWS, used_in=("S",))
    assert resolve_source(m, {"O:": str(vol)}) == vol / "Shoot/a.mov"
    assert resolve_source(m, {}) is None
    rep = execute(
        build_plan(Project("p", "t", media=[m]), PlanOptions(preserve_after_levels=1)),
        tmp_path / "out",
        mappings={"o:": str(vol)},
    )
    assert rep.count(Status.COPIED) == 1
    assert (tmp_path / "out/Shoot/a.mov").read_bytes() == b"w"


def test_byte_progress_reaches_100_percent_and_is_monotonic(tmp_path):
    proj, _ = make(tmp_path, {"a.mov": b"a" * 3000, "b.mov": b"b" * 5000})
    events = []
    execute(build_plan(proj, opts(tmp_path)), tmp_path / "out", on_progress=events.append)
    assert events[-1].bytes_done == events[-1].bytes_total == 2 * 8000
    done = [e.bytes_done for e in events]
    assert done == sorted(done)
    assert {e.phase for e in events} >= {"copying", "verifying", "done"}


def test_progress_reaches_100_percent_with_skips_and_missing(tmp_path):
    proj, _ = make(tmp_path, {"a.mov": b"a" * 100})
    proj.media.append(MediaRef(path="/nope/x.mov", path_style=PathStyle.POSIX, used_in=("S",)))
    plan = build_plan(proj, opts(tmp_path))
    execute(plan, tmp_path / "out")
    events = []
    execute(plan, tmp_path / "out", on_progress=events.append)  # all identical/missing now
    assert events[-1].bytes_done == events[-1].bytes_total


def test_cancel_before_start_and_midway(tmp_path):
    import threading

    proj, _ = make(tmp_path, {f"f{i}.mov": bytes([i]) * 1000 for i in range(4)})
    plan = build_plan(proj, opts(tmp_path))
    ev = threading.Event()
    ev.set()
    rep = execute(plan, tmp_path / "out1", cancel=ev)
    assert rep.count(Status.CANCELLED) == 4 and rep.cancelled and not rep.ok
    assert not list((tmp_path / "out1").rglob("*")) or not any(
        p.is_file() for p in (tmp_path / "out1").rglob("*")
    )

    ev2 = threading.Event()
    seen = []

    def stop_after_first(res):
        seen.append(res)
        ev2.set()

    rep2 = execute(plan, tmp_path / "out2", cancel=ev2, progress=stop_after_first)
    assert rep2.count(Status.COPIED) == 1 and rep2.count(Status.CANCELLED) == 3
    assert not list((tmp_path / "out2").rglob(f"*{PARTIAL_SUFFIX}"))
    assert len(rep2.path_map()) == 1  # only the finished file would be relinked


def test_parallel_matches_serial_and_keeps_plan_order(tmp_path):
    proj, _ = make(tmp_path, {f"d{i % 3}/f{i}.mov": bytes([i]) * (500 + i) for i in range(12)})
    plan = build_plan(proj, opts(tmp_path))
    serial = execute(plan, tmp_path / "s")
    par = execute(plan, tmp_path / "p", workers=4)
    assert [r.dest.relative_to(tmp_path / "p") for r in par.results] == [
        r.dest.relative_to(tmp_path / "s") for r in serial.results
    ]
    assert par.ok and par.count(Status.COPIED) == 12
    assert [r.sha256 for r in par.results] == [r.sha256 for r in serial.results]


def test_posix_folder_mapping_for_projects_from_another_mac(tmp_path):
    lib = tmp_path / "lib"
    (lib / "Original Media").mkdir(parents=True)
    (lib / "Original Media" / "a.mov").write_bytes(b"a")
    m = MediaRef(
        path="/Users/demo/Movies/L.fcpbundle/Ev/Original Media/a.mov",
        path_style=PathStyle.POSIX,
        used_in=("S",),
    )
    maps = {"/Users/demo/Movies/L.fcpbundle/Ev": str(lib)}
    assert resolve_source(m, maps) == lib / "Original Media" / "a.mov"
    assert (
        resolve_source(m, {"/users/demo/movies/l.fcpbundle/EV/": str(lib)})
        == lib / "Original Media" / "a.mov"
    )
    assert resolve_source(m, {"/Users/demo/Movies/L.fcp": str(lib)}) == Path(
        m.path
    )  # whole components only
    assert resolve_source(m, None) == Path(m.path)
    rep = execute(
        build_plan(Project("p", "t", media=[m]), PlanOptions(preserve_after_levels=6)),
        tmp_path / "out",
        mappings=maps,
    )
    assert rep.count(Status.COPIED) == 1


def test_file_appearing_during_copy_is_not_overwritten(tmp_path, monkeypatch):
    import shutil

    proj, _ = make(tmp_path, {"a.mov": b"x" * 10})
    dest = tmp_path / "out"
    target = dest / "src/a.mov"
    real = shutil.copystat

    def racing(s, d, **kw):
        real(s, d, **kw)
        target.write_bytes(b"SOMEONE ELSE")  # appears after the existence check

    monkeypatch.setattr(shutil, "copystat", racing)
    rep = execute(build_plan(proj, opts(tmp_path)), dest)
    assert rep.count(Status.CONFLICT) == 1
    assert target.read_bytes() == b"SOMEONE ELSE"
    assert not list(dest.rglob(f"*{PARTIAL_SUFFIX}"))


def test_copy_project_file_and_bundle(tmp_path):
    from media_collector.copier import copy_project_file

    f = tmp_path / "in" / "Show.prproj"
    f.parent.mkdir()
    f.write_bytes(b"project")
    out = tmp_path / "out"
    assert copy_project_file(f, out).status is Status.COPIED
    assert (out / "Show.prproj").read_bytes() == b"project"
    assert (
        copy_project_file(f, out).status is Status.SKIPPED_IDENTICAL
    )  # name taken by the same file
    (out / "Show.prproj").write_bytes(b"edited")
    assert (
        copy_project_file(f, out).status is Status.CONFLICT
    )  # ...or by a different one: never overwritten
    assert (out / "Show.prproj").read_bytes() == b"edited"
    assert copy_project_file(f, out, "Show_1.prproj").status is Status.COPIED

    b = tmp_path / "in" / "Cut.fcpxmld"
    b.mkdir()
    (b / "Info.fcpxml").write_text("<fcpxml/>")
    assert copy_project_file(b, out).status is Status.COPIED
    assert copy_project_file(b, out).status is Status.CONFLICT
    assert copy_project_file(b, out, "Cut_1.fcpxmld").status is Status.COPIED


def test_original_and_relinked_share_a_version_number(tmp_path):
    from media_collector.fsutil import next_version
    from media_collector.writers import relinked_name

    assert next_version(tmp_path, "Show.prproj", relinked_name) == 0
    (tmp_path / "Show.prproj").write_text("x")
    assert next_version(tmp_path, "Show.prproj", relinked_name) == 1
    (tmp_path / "Show_1_relinked.prproj").write_text("x")  # only the relinked twin exists for 1
    assert next_version(tmp_path, "Show.prproj", relinked_name) == 2


def test_destination_is_synced_periodically_and_cancel_stops_at_the_next_chunk(
    tmp_path, monkeypatch
):
    import threading

    from media_collector import copier

    proj, _ = make(tmp_path, {"big.mov": b"x" * 64})
    monkeypatch.setattr(copier, "CHUNK", 8)
    monkeypatch.setattr(copier, "SYNC_EVERY", 16)
    syncs = []
    cancel = threading.Event()
    real = os.fsync

    def fsync(fd):
        syncs.append(1)
        cancel.set()  # the user presses Cancel while the destination is flushing
        real(fd)

    monkeypatch.setattr(copier.os, "fsync", fsync)
    dest = tmp_path / "out"
    rep = execute(build_plan(proj, opts(tmp_path)), dest, cancel=cancel)
    assert rep.count(Status.CANCELLED) == 1
    assert len(syncs) == 1  # stopped at the next chunk, did not carry on to sync the rest
    assert not list(dest.rglob(f"*{PARTIAL_SUFFIX}"))  # the half-written file is removed
    assert not (dest / "src/big.mov").exists()


def test_periodic_sync_count(tmp_path, monkeypatch):
    from media_collector import copier

    proj, _ = make(tmp_path, {"big.mov": b"x" * 64})
    monkeypatch.setattr(copier, "CHUNK", 8)
    monkeypatch.setattr(copier, "SYNC_EVERY", 16)
    syncs = []
    real = os.fsync
    monkeypatch.setattr(copier.os, "fsync", lambda fd: (syncs.append(1), real(fd))[1])
    rep = execute(build_plan(proj, opts(tmp_path)), tmp_path / "out")
    assert rep.ok and len(syncs) == 5  # after chunks 2, 4, 6, 8 (16 bytes each) + the final flush
