from media_collector.model import MediaRef, PathStyle, Project, Role
from media_collector.plan import PlanOptions, build_plan, dest_relative


def ref(path, style=PathStyle.POSIX, **kw):
    return MediaRef(path=path, path_style=style, **kw)


def test_preserve_after_levels_posix():
    m = ref("/Volumes/Drive/Job/Shoot/A001/clip.mov")
    assert (
        dest_relative(m, PlanOptions(preserve_after_levels=0))
        == "Volumes/Drive/Job/Shoot/A001/clip.mov"
    )
    assert dest_relative(m, PlanOptions(preserve_after_levels=2)) == "Job/Shoot/A001/clip.mov"
    assert dest_relative(m, PlanOptions(preserve_after_levels=99)) == "clip.mov"


def test_windows_drive_and_unc_prefix():
    m = ref(r"\\?\N:\Media\Shoot\a.mxf", PathStyle.WINDOWS)
    assert dest_relative(m, PlanOptions(preserve_after_levels=0)) == "N/Media/Shoot/a.mxf"
    assert dest_relative(m, PlanOptions(preserve_after_levels=1)) == "Media/Shoot/a.mxf"


def test_flatten_and_project_subfolder():
    m = ref("/a/b/c.mov")
    opts = PlanOptions(preserve_after_levels=None, project_subfolder="MyProj")
    assert dest_relative(m, opts) == "MyProj/c.mov"


def test_collision_renamed_not_overwritten():
    p = Project(
        source="x",
        format="t",
        media=[ref("/a/x/clip.mov", used_in=("S",)), ref("/b/x/clip.mov", used_in=("S",))],
    )
    plan = build_plan(p, PlanOptions(preserve_after_levels=None))
    assert [c.dest_rel for c in plan.copies] == ["clip.mov", "clip_2.mov"]
    assert plan.renamed_on_collision == 1


def test_scope_and_sequences():
    a = ref("/m/a.mov", used_in=("S1",))
    b = ref("/m/b.mov", used_in=("S2",))
    c = ref("/m/c.mov")
    p = Project(source="x", format="t", media=[a, b, c])
    paths = lambda o: {x.source.path for x in build_plan(p, o).copies}
    assert paths(PlanOptions(include_unused=True)) == {"/m/a.mov", "/m/b.mov", "/m/c.mov"}
    assert paths(PlanOptions()) == {"/m/a.mov", "/m/b.mov"}  # default: used only
    assert paths(PlanOptions(sequences=("S2",))) == {"/m/b.mov"}
    # chosen sequences + unused: S1's media is excluded, but media no sequence uses is added
    assert paths(PlanOptions(sequences=("S2",), include_unused=True)) == {"/m/b.mov", "/m/c.mov"}


def test_proxies_follow_their_original_only_when_asked():
    o = ref("/m/a.mov", used_in=("S",), paired_paths=("/p/a.mp4",))
    px = ref("/p/a.mp4", role=Role.PROXY, paired_paths=("/m/a.mov",))
    p = Project(source="x", format="t", media=[o, px])
    assert {c.source.path for c in build_plan(p, PlanOptions()).copies} == {"/m/a.mov"}
    on = build_plan(p, PlanOptions(include_proxies=True))
    assert {c.source.path for c in on.copies} == {"/m/a.mov", "/p/a.mp4"}


def test_cache_never_copied_even_with_unused():
    p = Project(
        source="x",
        format="t",
        media=[
            ref("/m/a.mov", used_in=("S",)),
            ref("/m/Previews/r.mov", used_in=("S",), is_cache=True),
        ],
    )
    for unused in (True, False):
        plan = build_plan(p, PlanOptions(include_unused=unused))
        assert [c.source.path for c in plan.copies] == ["/m/a.mov"]
        assert plan.skipped_cache == 1


def test_dot_dot_components_cannot_escape_the_destination():
    for path, style in (
        ("/../../evil/x.mov", PathStyle.POSIX),
        ("/a/../../x.mov", PathStyle.POSIX),
        ("C:\\..\\..\\x.mov", PathStyle.WINDOWS),
    ):
        rel = dest_relative(ref(path, style), PlanOptions())
        assert ".." not in rel.split("/") and not rel.startswith("/")
    assert dest_relative(ref("/a/./b/../c/x.mov"), PlanOptions()) == "a/c/x.mov"


def test_project_folder_cannot_escape_either():
    m = ref("/a/x.mov")
    assert dest_relative(m, PlanOptions(project_subfolder="../../J/./K")) == "J/K/a/x.mov"
    assert dest_relative(m, PlanOptions(project_subfolder="/abs")) == "abs/a/x.mov"


def test_path_without_a_file_name_is_left_out_not_fatal():
    import pytest

    proj = Project(
        source="p", format="t", media=[ref("/", used_in=("S",)), ref("/a/ok.mov", used_in=("S",))]
    )
    plan = build_plan(proj, PlanOptions())
    assert [c.dest_rel for c in plan.copies] == ["a/ok.mov"] and plan.unusable == ["/"]
    with pytest.raises(ValueError):
        PlanOptions(preserve_after_levels=-1)


def test_project_file_lands_where_its_own_folder_lands():
    from pathlib import Path

    from media_collector.plan import project_folder_parts

    p = Path("/Users/x/Documents/Show/Show.prproj")
    assert project_folder_parts(p, PlanOptions(preserve_after_levels=0)) == [
        "Users",
        "x",
        "Documents",
        "Show",
    ]
    assert project_folder_parts(p, PlanOptions(preserve_after_levels=3)) == ["Show"]
    assert (
        project_folder_parts(p, PlanOptions(preserve_after_levels=4)) == []
    )  # above the cut: root
    assert project_folder_parts(p, PlanOptions(preserve_after_levels=None)) == []  # flatten
    assert project_folder_parts(
        p, PlanOptions(preserve_after_levels=3, project_subfolder="Job")
    ) == [
        "Job",
        "Show",
    ]
