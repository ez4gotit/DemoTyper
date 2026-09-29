"""Recorder backends that cannot run for real here: wf-recorder (a stand-in script that
behaves like it: writes a file, finishes it on SIGINT) and the host recorder's argv."""

from __future__ import annotations

import os
import sys

import pytest

from scenarioplay.loader.model import RecorderSpec
from scenarioplay.recorder.host import HostRecorder, default_source
from scenarioplay.recorder.wayland import WfRecorder

pytestmark = pytest.mark.integration

FAKE_WF = """#!/bin/bash
# Stand-in for wf-recorder: records until SIGINT, then finishes the file.
out=""
while [ $# -gt 0 ]; do case "$1" in -f) out="$2"; shift 2 ;; *) shift ;; esac; done
echo "$@" > "{log}"
trap 'echo finished > "$out"; exit 0' INT
while true; do sleep 0.1; done
"""


async def test_wf_recorder_segments_stop_on_sigint(tmp_path, monkeypatch):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    fake = bindir / "wf-recorder"
    fake.write_text(FAKE_WF.format(log=tmp_path / "args"))
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}:{os.environ['PATH']}")
    logs = []
    rec = WfRecorder(RecorderSpec(fps=25, crf=20), "eDP-1", tmp_path / "take",
                     lambda *a: logs.append(a))
    argv = rec.argv("/x/out.mkv")
    assert argv[:4] == ["wf-recorder", "-y", "-f", "/x/out.mkv"]
    assert ["-o", "eDP-1"] == argv[-2:] and "crf=20" in argv
    # The transport's environment was built before PATH changed; use the patched one.
    rec.transport.env["PATH"] = os.environ["PATH"]
    await rec.start()
    await rec.pause()
    await rec.resume()
    await rec.stop()
    assert len(rec.segments) == 2
    assert all(s.end is not None and s.end > s.start for s in rec.segments)
    assert [s.path.read_text() for s in rec.segments] == ["finished\n", "finished\n"]
    assert not rec.died


def test_host_recorder_grabs_the_workstation_window(tmp_path):
    rec = HostRecorder(RecorderSpec(fps=30), "title=Lab VM - VMware Workstation",
                       tmp_path, lambda *a: None)
    argv = rec.argv("out.mkv")
    if sys.platform == "win32":
        assert argv[argv.index("-f") + 1] == "gdigrab"
        assert "title=Lab VM - VMware Workstation" in argv
    else:
        assert argv[argv.index("-f") + 1] == "x11grab"
    assert default_source("Lab VM").startswith("title=Lab VM") or sys.platform != "win32"
