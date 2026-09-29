from __future__ import annotations

import pytest

from scenarioplay.console.driver import parse_status
from scenarioplay.console.tmux import parse_version, tmux_key
from scenarioplay.recorder.base import Timeline
from scenarioplay.report.formats import Chapter, Subtitle, chapters_txt, hms, srt, srt_time
from scenarioplay.report.masker import Masker


@pytest.mark.parametrize("name,expected", [
    ("C-c", "C-c"), ("C-d", "C-d"), ("M-x", "M-x"), ("Tab", "Tab"), ("tab", "Tab"),
    ("Escape", "Escape"), ("Esc", "Escape"), ("PageDown", "NPage"), ("F12", "F12"),
    ("Up", "Up"), ("C-M-a", "C-M-a"), ("Backspace", "BSpace"), ("Enter", "Enter"),
    ("q", "q"), ("C-Banana", None), ("F13", None),
])
def test_tmux_key(name, expected):
    assert tmux_key(name) == expected


def test_parse_version():
    assert parse_version("tmux 3.4") == (3, 4)
    assert parse_version("tmux 3.3a") == (3, 3)
    assert parse_version("tmux next-3.5") == (3, 5)


def test_parse_status():
    s = parse_status("7 0\n\t ls -la\n")
    assert (s.seq, s.exit_code, s.command) == (7, 0, "ls -la")
    s = parse_status("3 130\n")
    assert (s.seq, s.exit_code, s.command) == (3, 130, "")
    assert parse_status("") is None
    assert parse_status("garbage") is None


def test_time_formats():
    assert hms(83.9) == "00:01:23"
    assert hms(3725) == "01:02:05"
    assert srt_time(3725.0456) == "01:02:05,046"


def test_chapters_first_at_zero():
    text = chapters_txt([Chapter(2.1, "Task 1"), Chapter(65, "Task 2")])
    assert text == "00:00:00 Task 1\n00:01:05 Task 2\n"


def test_chapters_intro_when_first_is_late():
    text = chapters_txt([Chapter(30, "Task 1")])
    assert text.splitlines() == ["00:00:00 Intro", "00:00:30 Task 1"]


def test_srt():
    out = srt([Subtitle(1.5, 3.0, "b"), Subtitle(0, 1, "a")])
    assert out.startswith("1\n00:00:00,000 --> 00:00:01,000\na\n")
    assert "2\n00:00:01,500 --> 00:00:03,000\nb\n" in out


def test_timeline():
    t = Timeline()
    assert t.video_time(100) == 0
    t.t0 = 100.0
    assert t.video_time(112.5) == 12.5
    assert t.video_time(99) == 0


def test_timeline_with_paused_segments():
    from pathlib import Path

    from scenarioplay.recorder.base import Segment

    t = Timeline()
    t.segments = [Segment(Path("a"), start=100.0, end=110.0),
                  Segment(Path("b"), start=130.0)]            # paused 110 -> 130
    assert t.t0 == 100.0
    assert t.video_time(105) == 5
    assert t.video_time(120) == 10          # during the pause: where the video resumes
    assert t.video_time(131.5) == 11.5
    t.segments[0].duration = 9.8            # exact length after finalize wins
    assert t.video_time(131.5) == 11.3


def test_masker():
    m = Masker()
    m.register("hunter2")
    m.register("")
    assert m("pw=hunter2!") == "pw=****!"
