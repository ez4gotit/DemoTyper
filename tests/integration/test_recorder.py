"""The ffmpeg x11grab recorder against a real X display (skipped without one)."""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import time

import pytest

from scenarioplay.loader.model import RecorderSpec
from scenarioplay.recorder import X11Recorder

pytestmark = [
    pytest.mark.recording,
    pytest.mark.skipif(not os.environ.get("DISPLAY") or not shutil.which("ffmpeg"),
                       reason="needs $DISPLAY and ffmpeg"),
]


def _duration(path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", str(path)],
                         capture_output=True, text=True).stdout
    return float(out.strip())


async def test_record_stop_remux_and_frame0(tmp_path):
    logs = []
    rec = X11Recorder(RecorderSpec(), os.environ["DISPLAY"], tmp_path,
                      lambda level, msg: logs.append((level, msg)))
    before = time.time()
    await rec.start()
    started = time.time()
    await asyncio.sleep(2.0)
    stopped = time.time()
    await rec.stop()
    video = await rec.finalize(keep=True)

    assert video is not None and video.name == "video.mp4" and video.exists()
    assert not (tmp_path / "video.mkv").exists()
    t0 = rec.frame0_wall()
    # The first frame was captured after we asked ffmpeg to start and before start() returned.
    assert before - 0.1 <= t0 <= started + 0.1, (before, t0, started)
    # Video time = wall time - t0 (spec 13: chapter stamps within 0.5 s of the video).
    assert _duration(video) == pytest.approx(stopped - t0, abs=0.5)
    assert not rec.died


async def test_recorder_death_is_detected(tmp_path):
    rec = X11Recorder(RecorderSpec(), os.environ["DISPLAY"], tmp_path, lambda *a: None)
    died = asyncio.Event()
    rec.on_death = died.set
    await rec.start()
    rec.proc.kill()
    await asyncio.wait_for(died.wait(), 5)
    assert rec.died
    # The partial Matroska file still turns into a playable video.
    video = await rec.finalize(keep=True)
    assert video is not None and video.exists()
