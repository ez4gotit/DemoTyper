"""Text formats for the take folder: chapters (YouTube style) and SRT subtitles."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Chapter:
    time: float  # video seconds
    title: str
    caption: str | None = None


@dataclass
class Subtitle:
    start: float
    end: float
    text: str


def hms(seconds: float) -> str:
    s = int(max(0.0, seconds))
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def srt_time(seconds: float) -> str:
    ms = round(max(0.0, seconds) * 1000)
    h, m, s = ms // 3_600_000, ms % 3_600_000 // 60_000, ms % 60_000 // 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms % 1000:03d}"


def chapters_txt(chapters: list[Chapter], intro_title: str = "Intro") -> str:
    """YouTube chapter list. YouTube needs the first chapter at 00:00:00, so a first chapter
    that starts within 5 s is moved there; a later one gets an intro chapter before it."""
    if not chapters:
        return ""
    lines = []
    items = sorted(chapters, key=lambda c: c.time)
    if items[0].time > 5.0:
        lines.append(f"00:00:00 {intro_title}")
    for i, ch in enumerate(items):
        t = 0.0 if i == 0 and ch.time <= 5.0 else ch.time
        lines.append(f"{hms(t)} {ch.title}")
    return "\n".join(lines) + "\n"


def srt(subtitles: list[Subtitle]) -> str:
    out = []
    for i, sub in enumerate(sorted(subtitles, key=lambda s: s.start), start=1):
        out.append(f"{i}\n{srt_time(sub.start)} --> {srt_time(sub.end)}\n{sub.text}\n")
    return "\n".join(out)
