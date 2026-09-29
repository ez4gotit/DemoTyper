"""Run modes (spec 11, 10.3): --from/--to, --step, --cast, --burn-subtitles."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

import pytest

from scenarioplay.engine.selection import select
from scenarioplay.exitcodes import ExitCode
from scenarioplay.loader import load_scenario

from .conftest import FAST

pytestmark = pytest.mark.integration

CHAPTERS = FAST + """
steps:
  - chapter: "One"
  - run: "echo in-one"
  - chapter: "Two"
  - run: "echo in-two-a"
    label: two-a
  - run: "echo in-two-b"
  - chapter: "Three"
  - run: "echo in-three"
"""


def test_select_by_chapter_and_label(write_scenario):
    parsed, _ = load_scenario(write_scenario(CHAPTERS))
    steps = parsed.sections["steps"]
    assert select(steps, "Two", "Two") == (2, 5)
    assert len(steps) == 7
    assert select(steps, "two-a", None) == (3, 7)
    assert select(steps, None, "two-a") == (0, 4)
    with pytest.raises(ValueError, match="available: 'One', 'Two', 'two-a', 'Three'"):
        select(steps, "Four", None)
    with pytest.raises(ValueError, match="comes before"):
        select(steps, "Three", "One")


async def test_from_to_runs_only_that_part(play):
    r = await play(CHAPTERS, fast=False, from_name="Two", to_name="Two")
    assert r.code == ExitCode.OK, r.log
    assert "in-two-a" in r.transcript and "in-two-b" in r.transcript
    assert "in-one" not in r.transcript and "in-three" not in r.transcript
    assert "running steps 3-5 of 7" in r.log


def test_step_mode_asks_before_each_step(write_scenario, tmp_path):
    path = write_scenario(FAST + """
steps:
  - run: "echo first-step"
  - run: "echo second-step"
  - run: "echo third-step"
  - run: "echo fourth-step"
""")
    out = tmp_path / "takes"
    proc = subprocess.run(
        [sys.executable, "-m", "scenarioplay.cli", "run", str(path), "--headless", "--step",
         "--out", str(out)],
        input="\ns\nc\n", capture_output=True, text=True, timeout=120,
        env={**os.environ, "PYTHONUNBUFFERED": "1"})
    assert proc.returncode == 0, proc.stderr
    assert proc.stderr.count("[Enter] run") == 3  # the third answer stops the asking
    transcript = next(out.glob("*/transcript/main.txt")).read_text()
    assert "first-step" in transcript and "second-step" not in transcript
    assert "third-step" in transcript and "fourth-step" in transcript


def test_step_mode_quit(write_scenario, tmp_path):
    path = write_scenario(FAST + "steps:\n  - run: \"echo never\"\n")
    out = tmp_path / "takes"
    proc = subprocess.run(
        [sys.executable, "-m", "scenarioplay.cli", "run", str(path), "--headless", "--step",
         "--out", str(out)], input="q\n", capture_output=True, text=True, timeout=120)
    assert proc.returncode == ExitCode.INTERRUPTED


async def test_cast_files(play):
    r = await play(FAST + """
layout: split-horizontal
consoles: [{name: main}, {name: side}]
steps:
  - run: "echo hello-cast"
  - run: "echo side-cast"
    console: side
""", fast=False, cast=True)
    assert r.code == ExitCode.OK, r.log
    lines = (r.dir / "cast" / "main.cast").read_text().splitlines()
    header = json.loads(lines[0])
    assert header["version"] == 2 and header["width"] > 10
    events = [json.loads(line) for line in lines[1:]]
    assert all(e[1] == "o" for e in events)
    assert [e[0] for e in events] == sorted(e[0] for e in events)
    assert "hello-cast" in "".join(e[2] for e in events)
    side = (r.dir / "cast" / "side.cast").read_text()
    assert "side-cast" in side and "hello-cast" not in side


def _has_libass() -> bool:
    out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True,
                         text=True).stdout
    return " subtitles " in out


@pytest.mark.recording
@pytest.mark.skipif(not os.environ.get("DISPLAY") or not shutil.which("ffmpeg")
                    or os.environ.get("WAYLAND_DISPLAY") is not None,
                    reason="needs an X display (not XWayland) and ffmpeg")
async def test_burn_subtitles(play):
    if not _has_libass():
        pytest.skip("ffmpeg without libass")
    from scenarioplay.console.terminal import find_terminal

    if not find_terminal():
        pytest.skip("no terminal emulator")
    r = await play(FAST + """
target: {recorder: {lead_in: 0.5, tail: 0.5}}
steps:
  - chapter: "Burned in"
  - run: "echo subtitled"
""", fast=False, record=True, headless=False, burn_subtitles=True)
    assert r.code == ExitCode.OK, r.log
    assert (r.dir / "video.mp4").exists() and (r.dir / "video.clean.mp4").exists()
    assert "subtitles burned into video.mp4" in r.log
