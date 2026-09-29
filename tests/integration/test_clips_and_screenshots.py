"""record: start/stop clips, screenshots of one console, text snapshots, automatic chapter
screenshots."""

from __future__ import annotations

import json
import os
import shutil
import subprocess

import pytest

from scenarioplay.console.terminal import find_terminal
from scenarioplay.exitcodes import ExitCode

from .conftest import FAST

pytestmark = pytest.mark.integration


def _png_size(path) -> tuple[int, int]:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True,
                         check=True).stdout.strip()
    w, h = out.split(",")
    return int(w), int(h)


def _duration(path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", str(path)], capture_output=True,
                         text=True, check=True).stdout
    return float(out)


# --- headless: text snapshots ---------------------------------------------------------

async def test_headless_screenshots_are_text_snapshots(play):
    r = await play(FAST + """
layout: split-horizontal
consoles: [{name: main, title: "Main"}, {name: side, title: "Side"}]
steps:
  - run: "printf '\\\\033[31mred text\\\\033[0m\\\\n'"
  - run: "echo on-the-side"
    console: side
  - screenshot: both.png
  - screenshot: {file: only-side, console: side}
  - record: stop                      # no-op without recording
""", fast=False)
    assert r.code == ExitCode.OK, r.log
    shots = r.dir / "screenshots"
    both = (shots / "both.html").read_text()
    assert "<h2>Main</h2>" in both and "<h2>Side</h2>" in both
    assert '<span style="color:#cd0000">red text</span>' in both
    side = (shots / "only-side.txt").read_text()
    assert "on-the-side" in side and "red text" not in side
    assert "not recording in this take" in r.log


async def test_automatic_chapter_screenshots_headless(play):
    r = await play(FAST + """  screenshots: {chapters: both}
steps:
  - chapter: "Install"
  - run: "echo installing"
  - chapter: "Check it"
  - run: "echo checking"
""", fast=False)
    assert r.code == ExitCode.OK, r.log
    names = sorted(p.name for p in (r.dir / "screenshots").glob("*.txt"))
    assert names == ["01-install-end.txt", "01-install-start.txt",
                     "02-check-it-end.txt", "02-check-it-start.txt"]
    end = (r.dir / "screenshots" / "01-install-end.txt").read_text()
    assert "installing" in end and "checking" not in end


# --- recorded: clips, cropped PNGs ----------------------------------------------------

recorded = pytest.mark.skipif(
    not os.environ.get("DISPLAY") or not shutil.which("ffmpeg") or not find_terminal()
    or os.environ.get("WAYLAND_DISPLAY") is not None,
    reason="needs an X display (not XWayland), ffmpeg and a terminal")


@pytest.mark.recording
@recorded
async def test_clips_start_stop_and_late_start(play):
    r = await play(FAST + """
target:
  recorder: {lead_in: 0.3, tail: 0.3, autostart: false}
steps:
  - run: "echo not-in-any-video"
  - record: start
    clip: intro
  - chapter: "Intro"
  - run: "echo intro"
  - record: stop
  - run: "sleep 3"
    timeout: 20
  - chapter: "Main part"             # while stopped: opens the next clip
  - record: start
    clip: main part
  - run: "echo main"
""", fast=False, record=True, headless=False)
    assert r.code == ExitCode.OK, r.log
    clips = r.dir / "clips"
    assert sorted(p.name for p in clips.glob("*.mp4")) == ["01-intro.mp4", "02-main-part.mp4"]
    assert not (r.dir / "video.mp4").exists()
    assert (clips / "01-intro.chapters.txt").read_text() == "00:00:00 Intro\n"
    assert (clips / "02-main-part.chapters.txt").read_text() == "00:00:00 Main part\n"
    assert "Main part" in (clips / "02-main-part.srt").read_text()
    report = json.loads((r.dir / "report.json").read_text())
    assert [c["name"] for c in report["clips"]] == ["intro", "main part"]
    steps = {s["summary"]: s for s in report["steps"]}
    assert steps["run: echo not-in-any-video"]["video_time"] is None
    assert steps["run: echo intro"]["clip"] == 1 and steps["run: echo main"]["clip"] == 2
    # The 3 s sleep between the clips is in neither of them.
    assert _duration(clips / "01-intro.mp4") < 5 and _duration(clips / "02-main-part.mp4") < 5


@pytest.mark.recording
@recorded
async def test_png_screenshots_cropped_to_a_console(play):
    r = await play(FAST + """  screenshots: {chapters: end}
target:
  recorder: {lead_in: 0.3, tail: 0.3}
  terminal:
    command: ["xterm", "-geometry", "120x40+0+0", "-fa", "DejaVu Sans Mono", "-fs", "11",
              "-e"]
layout: split-horizontal
consoles: [{name: left, title: "Left"}, {name: right, title: "Right"}]
steps:
  - chapter: "Only chapter"
  - run: "echo on-the-left"
  - run: "echo on-the-right"
    console: right
  - screenshot: full.png
  - screenshot: {file: right-only.png, console: right, text: true}
  - record: stop
  - screenshot: after-stop.png       # works without a running recording
""", fast=False, record=True, headless=False)
    assert r.code == ExitCode.OK, r.log
    shots = r.dir / "screenshots"
    full_w, full_h = _png_size(shots / "full.png")
    right_w, right_h = _png_size(shots / "right-only.png")
    assert right_w < full_w * 0.6 and right_h <= full_h
    assert right_w > 100 and right_h > 100
    assert "on-the-right" in (shots / "right-only.txt").read_text()
    assert "on-the-left" not in (shots / "right-only.txt").read_text()
    assert (shots / "after-stop.png").exists()
    assert (shots / "01-only-chapter-end.png").exists()
    assert (r.dir / "video.mp4").exists()  # one clip: the usual file name
