"""A complete recorded take: terminal window, tmux, typing, ffmpeg, take folder.

Needs an X display, ffmpeg and a terminal emulator (CI runs it under Xvfb with xterm).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess

import pytest

from scenarioplay.console.terminal import find_terminal
from scenarioplay.engine.context import RunOptions
from scenarioplay.engine.take import run_take
from scenarioplay.exitcodes import ExitCode
from scenarioplay.loader import load_scenario

pytestmark = [
    pytest.mark.integration,
    pytest.mark.recording,
    pytest.mark.skipif(not os.environ.get("DISPLAY") or not shutil.which("ffmpeg")
                       or not find_terminal(), reason="needs $DISPLAY, ffmpeg and a terminal"),
]


def _duration(path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


async def test_recorded_take(write_scenario, tmp_path):
    path = write_scenario("""
        meta: {title: "Recorded"}
        target:
          recorder: {lead_in: 1, tail: 1}
        defaults:
          typing: {profile: expert}
          after_command_pause: 0.3
        steps:
          - chapter: "One"
          - run: "echo first"
          - chapter: "Two"
            caption: "second chapter"
          - run: "echo second"
            expect: '^second$'
    """)
    parsed, problems = load_scenario(path)
    assert parsed is not None, problems
    out = tmp_path / "takes"
    code = await run_take(parsed, RunOptions(record=True, out_dir=out))
    take = next(out.iterdir())
    report = json.loads((take / "report.json").read_text())
    assert code == ExitCode.OK, (take / "take.log").read_text()

    video = take / "video.mp4"
    assert report["video"] == "video.mp4" and video.exists()
    duration = _duration(video)
    chapters = report["chapters"]
    assert [c["title"] for c in chapters] == ["One", "Two"]
    # Lead-in of 1 s before the first chapter; every chapter lies inside the video.
    assert chapters[0]["time"] == pytest.approx(1.0, abs=0.5)
    assert all(0 <= c["time"] < duration for c in chapters)
    assert (take / "chapters.txt").read_text().startswith("00:00:00 One\n")
    assert "second chapter" in (take / "subtitles.srt").read_text()
    assert "echo second" in (take / "transcript" / "main.txt").read_text()

    # The last frame must show the terminal's text, not an empty screen.
    frame = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{duration - 0.5:.2f}", "-i", str(video),
         "-frames:v", "1", "-vf", "format=gray", "-f", "rawvideo", "-"],
        capture_output=True, check=True).stdout
    if max(frame) < 24 and os.environ.get("WAYLAND_DISPLAY"):
        pytest.skip("XWayland display: x11grab records black here (WSLg); use Xvfb or Xorg")
    assert max(frame) >= 24, "the video is black: the screen capture saw nothing"
    lit = sum(1 for b in frame if b > 100) / len(frame)
    assert 0 < lit < 0.5, f"{lit:.1%} of pixels are bright; expected text on a dark terminal"


async def test_record_pause_and_resume(write_scenario, tmp_path):
    path = write_scenario("""
        target:
          recorder: {lead_in: 0.5, tail: 0.5}
        defaults:
          typing: {profile: robot}
          after_command_pause: 0
        steps:
          - chapter: "Before"
          - run: "echo one"
          - record: pause
          - run: "sleep 4"
            timeout: 30
          - record: resume
          - chapter: "After"
          - run: "echo two"
    """)
    parsed, problems = load_scenario(path)
    assert parsed is not None, problems
    out = tmp_path / "takes"
    code = await run_take(parsed, RunOptions(record=True, out_dir=out))
    take = next(out.iterdir())
    assert code == ExitCode.OK, (take / "take.log").read_text()
    report = json.loads((take / "report.json").read_text())
    duration = _duration(take / "video.mp4")
    wall = report["duration"]
    assert not list(take.glob("*.mkv"))  # segments were joined and removed
    # About 4 s of `sleep` is cut out of the video.
    assert wall - duration > 3.0, (wall, duration)
    before, after = report["chapters"]
    assert after["time"] - before["time"] < 3.0  # the pause does not count
    assert after["time"] < duration
    assert "skipped)" in (take / "subtitles.srt").read_text()
