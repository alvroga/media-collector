"""Drives `media_collector serve` as a subprocess over JSON lines, exactly as the app will."""

import gzip
import json
import queue
import subprocess
import sys
import threading
from pathlib import Path

import pytest

XML = """<?xml version="1.0" encoding="UTF-8" ?>
<PremiereData Version="3">
\t<Project ObjectRef="1"/>
\t<Sequence ObjectUID="seq-1" ClassID="c" Version="1">
\t\t<Name>Edit One</Name>
\t\t<Link ObjectURef="m-a"/>
\t\t<Link ObjectURef="m-b"/>
\t\t<Link ObjectURef="m-w"/>
\t</Sequence>
\t<Media ObjectUID="m-a" ClassID="c" Version="30">
\t\t<ActualMediaFilePath>{a}</ActualMediaFilePath>
\t\t<FilePath>{a}</FilePath>
\t\t<RelativePath>./a.mov</RelativePath>
\t</Media>
\t<Media ObjectUID="m-b" ClassID="c" Version="30">
\t\t<ActualMediaFilePath>{b}</ActualMediaFilePath>
\t\t<FilePath>{b}</FilePath>
\t</Media>
\t<Media ObjectUID="m-w" ClassID="c" Version="30">
\t\t<ActualMediaFilePath>O:\\Shoot\\w.mov</ActualMediaFilePath>
\t\t<FilePath>O:\\Shoot\\w.mov</FilePath>
\t</Media>
\t<Media ObjectUID="m-u" ClassID="c" Version="30">
\t\t<ActualMediaFilePath>{u}</ActualMediaFilePath>
\t\t<FilePath>{u}</FilePath>
\t</Media>
</PremiereData>
"""


class Client:
    def __init__(self):
        self.p = subprocess.Popen(
            [sys.executable, "-m", "media_collector", "serve"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self.q: queue.Queue = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()
        self.next_id = 1
        self.events: list[dict] = []
        self.ready = self.q.get(timeout=20)

    def _pump(self):
        for line in self.p.stdout:
            self.q.put(json.loads(line))

    def send(self, cmd, **args) -> int:
        rid = self.next_id
        self.next_id += 1
        self.p.stdin.write(json.dumps({"id": rid, "cmd": cmd, **args}) + "\n")
        self.p.stdin.flush()
        return rid

    def wait(self, rid, timeout=60):
        while True:
            m = self.q.get(timeout=timeout)
            if m.get("id") == rid and "ok" in m:
                return m
            self.events.append(m)

    def call(self, cmd, **args):
        return self.wait(self.send(cmd, **args))

    def close(self):
        self.p.stdin.close()
        self.p.wait(timeout=20)


@pytest.fixture
def client():
    c = Client()
    yield c
    try:
        c.close()
    except (OSError, subprocess.SubprocessError):
        c.p.kill()


@pytest.fixture
def project(tmp_path):
    src = tmp_path / "media"
    src.mkdir()
    (src / "a.mov").write_bytes(b"a" * 1000)
    (src / "b.mov").write_bytes(b"b" * 2000)
    (src / "unused.mov").write_bytes(b"u" * 10)
    win = tmp_path / "vol" / "Shoot"
    win.mkdir(parents=True)
    (win / "w.mov").write_bytes(b"w" * 500)
    proj = tmp_path / "p.prproj"
    with gzip.open(proj, "wt") as f:
        f.write(XML.format(a=src / "a.mov", b=src / "b.mov", u=src / "unused.mov"))
    return proj, tmp_path


def test_ready_and_basic_errors(client):
    assert client.ready == {"event": "ready", "protocol": 1, "version": client.ready["version"]}
    assert client.call("volumes")["ok"]
    r = client.call("nope")
    assert not r["ok"] and "unknown command" in r["error"]
    r = client.call("plan")
    assert not r["ok"] and "no project open" in r["error"]
    client.p.stdin.write("garbage\n")
    client.p.stdin.flush()
    assert client.q.get(timeout=10)["event"] == "error"


def test_open_and_plan(client, project):
    proj, tmp = project
    r = client.call("open_project", path=str(proj))
    assert r["ok"], r
    res = r["result"]
    assert res["format"] == "premiere"
    assert [s["name"] for s in res["sequences"]] == ["Edit One"]
    assert res["sequences"][0]["originals"] == 3
    assert res["unused"] == 1
    assert res["unmapped_prefixes"] == [{"prefix": "O:", "files": 1}]

    plan = client.call("plan", options={"keep_from_level": 0})["result"]
    assert plan["files"] == 3 and plan["bytes"] == 3000
    assert plan["missing"]["count"] == 1 and plan["missing"]["items"][0]["reason"] == "unmapped"
    assert plan["unmapped_prefixes"] == [{"prefix": "O:", "files": 1}]

    mapped = client.call(
        "plan", options={"include_unused": True}, mappings={"O:": str(tmp / "vol")}
    )["result"]
    assert mapped["files"] == 4 and mapped["missing"]["count"] == 0
    assert mapped["bytes"] == 3510 and mapped["unmapped_prefixes"] == []
    assert mapped["examples"]

    bad = client.call("plan", options={"bogus": 1})
    assert not bad["ok"] and "unknown option" in bad["error"]
    assert not client.call("plan", options={"keep_from_level": -1})["ok"]


def test_run_with_progress_and_relink(client, project):
    proj, tmp = project
    client.call("open_project", path=str(proj))
    dest = tmp / "out"
    dest.mkdir()
    r = client.call(
        "run",
        dest=str(dest),
        mappings={"O:": str(tmp / "vol")},
        workers=2,
        relink=True,
        options={"keep_from_level": len(tmp.parts) - 1},
    )
    assert r["ok"], r
    res = r["result"]
    assert res["ok"] and res["counts"] == {"copied": 3} and res["bytes"] == 3500
    prog = [e for e in client.events if e["event"] == "progress"]
    assert prog and prog[-1]["bytes_done"] == prog[-1]["bytes_total"] == 7000
    assert len([e for e in client.events if e["event"] == "file"]) == 3
    relinked = Path(res["relinked_project"])
    assert (
        relinked.exists()
        and res["relink"]["relinked"] == 3
        and res["relink"]["left_unchanged"] == 1
    )
    assert (dest / "media/a.mov").read_bytes() == b"a" * 1000
    assert relinked.parent == dest and relinked.name.endswith("_relinked" + proj.suffix)
    assert res["project_copy"]["status"] == "copied" and (dest / proj.name).exists()
    # second run: everything identical; relink refuses to overwrite the existing project
    r2 = client.call(
        "run",
        dest=str(dest),
        mappings={"O:": str(tmp / "vol")},
        relink=True,
        options={"keep_from_level": len(tmp.parts) - 1},
    )["result"]
    assert r2["counts"] == {"skipped_identical": 3}
    # Nothing is overwritten: the second run's original and relinked project share the next number.
    assert Path(r2["project_copy"]["path"]).name == f"{proj.stem}_1{proj.suffix}"
    assert Path(r2["relinked_project"]).name == f"{proj.stem}_1_relinked{proj.suffix}"
    assert relinked.exists()


def test_missing_source_blocks_relink(client, project):
    proj, tmp = project
    client.call("open_project", path=str(proj))
    res = client.call("run", dest=str(tmp / "out2"), relink=True)[
        "result"
    ]  # O: unmapped -> missing
    assert not res["ok"] and res["counts"]["missing"] == 1
    assert res["relinked_project"] is None and "skipped" in res["relink"]
    assert res["problems"][0]["status"] == "missing"


def test_cancel_and_busy(client, tmp_path):
    big = tmp_path / "media" / "big.mov"
    big.parent.mkdir()
    with open(big, "wb") as f:
        f.writelines(b"\0" * (4 * 1024 * 1024) for _ in range(64))  # 256 MB
    proj = tmp_path / "big.prproj"
    with gzip.open(proj, "wt") as f:
        f.write(XML.format(a=big, b=big, u=big).replace("O:\\\\Shoot\\\\w.mov", str(big)))
    client.call("open_project", path=str(proj))
    dest = tmp_path / "out"
    rid = client.send("run", dest=str(dest), options={"keep_from_level": 0})
    while True:  # wait until bytes are actually flowing
        m = client.q.get(timeout=30)
        client.events.append(m)
        if m.get("event") == "progress":
            break
    busy = client.call("plan")
    assert not busy["ok"] and "busy" in busy["error"]
    assert client.call("cancel")["result"]["cancelling"] is True
    res = client.wait(rid)["result"]
    assert res["cancelled"] and not res["ok"]
    assert not list(dest.rglob("*.mc-partial"))
    assert not client.call("cancel")["result"]["cancelling"]  # nothing running now


def test_client_going_away_is_quiet(tmp_path):
    import io

    from media_collector.server import Server

    class DeadPipe(io.StringIO):
        def write(self, _s):
            raise BrokenPipeError

    srv = Server(io.StringIO('{"id":1,"cmd":"volumes"}\n'), DeadPipe())
    assert srv.serve() == 0  # no exception, no traceback
    assert srv._gone and srv._cancel.is_set()


def test_open_bundle_and_info_fcpxml_and_explain_unsupported(client, tmp_path):
    from test_readers import FCPXML

    bundle = tmp_path / "x.fcpxmld"
    bundle.mkdir()
    (bundle / "Info.fcpxml").write_text(FCPXML)
    for given in (bundle, bundle / "Info.fcpxml"):
        r = client.call("open_project", path=str(given))
        assert r["ok"], r
        assert r["result"]["format"] == "fcpxml" and r["result"]["path"] == str(bundle)
    lib = tmp_path / "Lib.fcpbundle"
    lib.mkdir()
    r = client.call("open_project", path=str(lib))
    assert not r["ok"] and "Export XML" in r["error"]
    r = client.call("open_project", path=str(tmp_path / "missing.prproj"))
    assert not r["ok"] and "not found" in r["error"]


def test_can_relink_and_sequences_reported_per_format(client, tmp_path):
    from test_readers import FCPXML

    fcp = tmp_path / "p.fcpxml"
    fcp.write_text(FCPXML)
    r = client.call("open_project", path=str(fcp))["result"]
    assert r["can_relink"] is True and len(r["sequences"]) == 2
    aep = tmp_path / "x.aep"
    aep.write_bytes(
        b"RIFX\x00\x00\x01\x00Egg!"
        b'{"ascendcount_base":1,"ascendcount_target":3,"fullpath":"/m/a.mov","platform":2,"target_is_folder":false}'
    )
    r = client.call("open_project", path=str(aep))["result"]
    assert r["can_relink"] is False and r["sequences"] == [] and r["files"] == 1
    assert r["warnings"] == []
    plan = client.call("plan", options={})["result"]
    assert plan["files"] == 1  # footage still counts as used with no sequences


def test_relinked_project_goes_into_the_project_folder(client, project):
    from media_collector.writers import relinked_name

    proj, tmp = project
    client.call("open_project", path=str(proj))
    dest = tmp / "out"
    dest.mkdir()
    r = client.call(
        "run",
        dest=str(dest),
        mappings={"O:": str(tmp / "vol")},
        relink=True,
        options={"keep_from_level": len(tmp.parts) - 1, "project_folder": "Job 1"},
    )["result"]
    assert r["ok"] and Path(r["relinked_project"]) == dest / "Job 1" / relinked_name(proj.name)
    assert r["project_copy"]["status"] == "copied"
    assert (
        dest / "Job 1" / proj.name
    ).read_bytes() == proj.read_bytes()  # original, untouched content
    assert (dest / "Job 1" / "media/a.mov").exists()


def test_project_files_sit_in_their_mapped_source_folder(client, project):
    proj, tmp = project
    client.call("open_project", path=str(proj))
    dest = tmp / "out"
    dest.mkdir()
    # keep everything from the project's own folder down: the project sits at the top of the media tree
    skip = len(proj.parent.parts) - 2  # keep only the project's own folder name
    r = client.call(
        "run",
        dest=str(dest),
        mappings={"O:": str(tmp / "vol")},
        relink=True,
        options={"keep_from_level": skip},
    )["result"]
    folder = dest / proj.parent.name
    assert Path(r["project_copy"]["path"]) == folder / proj.name
    assert Path(r["relinked_project"]).parent == folder
