import pytest

from media_collector import fsutil
from media_collector.fsutil import move_no_clobber


@pytest.mark.parametrize("native", [True, False])
def test_move_no_clobber(tmp_path, monkeypatch, native):
    if not native:
        monkeypatch.setattr(fsutil, "_RENAME", None)  # the check-then-replace fallback
    a, b = tmp_path / "a", tmp_path / "b"
    a.write_bytes(b"new")
    move_no_clobber(a, b)
    assert b.read_bytes() == b"new" and not a.exists()
    c = tmp_path / "c"
    c.write_bytes(b"other")
    with pytest.raises(FileExistsError):
        move_no_clobber(c, b)
    assert b.read_bytes() == b"new" and c.exists()
