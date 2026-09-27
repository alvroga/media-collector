from pathlib import Path

import pytest

from media_collector.cli import main

SIMPLE = Path(__file__).parent.parent / "assets" / "296800_1.prproj"


@pytest.mark.skipif(not SIMPLE.exists(), reason="sample project not present")
def test_inspect_and_dry_run(capsys, tmp_path):
    assert main(["inspect", str(SIMPLE)]) == 0
    assert "2 sequences" in capsys.readouterr().out
    # sources are offline here, so a dry run reports them missing (exit 1) but writes nothing
    assert main(["copy", str(SIMPLE), str(tmp_path / "out"), "--dry-run"]) == 1
    assert not (tmp_path / "out").exists()


def test_unsupported_format(tmp_path):
    f = tmp_path / "x.edl"
    f.write_bytes(b"")
    with pytest.raises(ValueError):
        main(["inspect", str(f)])


def test_bad_arguments_are_usage_errors(tmp_path):
    for extra in (["--map", "nonsense"], ["--keep-from-level", "-1"]):
        with pytest.raises(SystemExit) as e:
            main(["copy", "p.prproj", str(tmp_path), *extra])
        assert e.value.code == 2
