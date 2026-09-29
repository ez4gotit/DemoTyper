"""Writes the take folder (spec section 10.2): log, chapters, subtitles, report, transcripts."""

from __future__ import annotations

import json
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO

import click

from ..recorder.base import Segment, Timeline
from .formats import Chapter, Subtitle, chapters_txt, srt
from .masker import Masker

LEVELS = {"debug": 10, "info": 20, "warning": 30, "error": 40}
CHAPTER_SUBTITLE_SECONDS = 4.0


@dataclass
class Clip:
    """One video file of the take (`record: stop` / `record: start` make several)."""

    index: int
    name: str
    timeline: Timeline
    start: float  # wall clock of `record: start`
    end: float | None = None  # wall clock of `record: stop`
    video: str | None = None  # path in the take folder, once finalized

    @property
    def stem(self) -> str:
        slug = re.sub(r"[^A-Za-z0-9]+", "-", self.name).strip("-").lower()[:40]
        return f"{self.index:02d}-{slug or 'clip'}"


@dataclass
class StepRecord:
    path: str
    section: str
    action: str
    summary: str
    label: str | None
    line: int | None
    started: float  # wall clock
    status: str = "running"  # ok | failed | failed-continued | interrupted
    duration: float = 0.0
    error: str | None = None
    notes: list[str] = field(default_factory=list)


class Reporter:
    def __init__(self, take_dir: Path, *, verbose: bool = False, echo: TextIO | None = None):
        self.take_dir = take_dir
        take_dir.mkdir(parents=True, exist_ok=True)
        self.mask = Masker()
        self.verbose = verbose
        self.echo = echo if echo is not None else sys.stderr
        self._log = open(take_dir / "take.log", "w", encoding="utf-8", buffering=1)
        self.started = time.time()
        self.timeline = Timeline()
        self.clips: list[Clip] = []
        self._chapters: list[tuple[float, str, str | None]] = []  # wall, title, caption
        self._captions: list[tuple[float, str, float]] = []  # wall, text, duration
        self.steps: list[StepRecord] = []

    # --- log ---------------------------------------------------------------------------

    def log(self, level: str, message: str) -> None:
        if level == "debug" and not self.verbose:
            return
        message = self.mask(message)
        now = time.time()
        stamp = datetime.fromtimestamp(now).strftime("%H:%M:%S.%f")[:-3]
        line = f"{stamp} +{now - self.started:8.3f}s {level.upper():7} {message}"
        self._log.write(line + "\n")
        if LEVELS[level] >= LEVELS["info"] or self.verbose:
            color = {"warning": "yellow", "error": "red", "debug": "bright_black"}.get(level)
            click.secho(line, file=self.echo, fg=color)

    # --- timeline events ---------------------------------------------------------------

    def chapter(self, title: str, caption: str | None) -> None:
        self._chapters.append((time.time(), self.mask(title),
                               self.mask(caption) if caption else None))
        self.log("info", f"=== chapter: {title}")

    def caption(self, text: str, duration: float) -> None:
        self._captions.append((time.time(), self.mask(text), duration))
        self.log("info", f"caption: {text}")

    def step_started(self, record: StepRecord) -> None:
        self.steps.append(record)
        where = f" (line {record.line})" if record.line else ""
        label = f" [{record.label}]" if record.label else ""
        self.log("info", f"step {record.path}{label}{where}: {record.summary}")

    # --- outputs -----------------------------------------------------------------------

    # --- clips ----------------------------------------------------------------------

    def add_clip(self, name: str, segments: list[Segment]) -> Clip:
        """A new video clip (`record: start`). Its timeline shares the recorder's segments."""
        timeline = Timeline()
        timeline.segments = segments
        clip = Clip(len(self.clips) + 1, name, timeline, time.time())
        self.clips.append(clip)
        self.timeline = timeline  # steps and events from now on belong to this clip
        return clip

    def _clip_of(self, wall: float) -> Clip | None:
        """The clip an event at `wall` belongs to: the one running then, or the next one
        (a chapter started while recording was stopped opens the next clip). None for
        events after the last clip ended."""
        for clip in self.clips:
            if clip.end is None or wall <= clip.end:
                return clip
        return None

    def _events(self, clip: Clip | None) -> tuple[list[Chapter], list[Subtitle]]:
        timeline = clip.timeline if clip is not None else self.timeline
        vt = timeline.video_time
        chapters, subs = [], []
        for wall, title, caption in self._chapters:
            if clip is not None and self._clip_of(wall) is not clip:
                continue
            chapters.append(Chapter(vt(wall), title, caption))
            text = title + (f"\n{caption}" if caption else "")
            subs.append(Subtitle(vt(wall), vt(wall) + CHAPTER_SUBTITLE_SECONDS, text))
        for wall, text, duration in self._captions:
            if clip is not None and self._clip_of(wall) is not clip:
                continue
            subs.append(Subtitle(vt(wall), vt(wall) + duration, text))
        return chapters, subs

    def chapters(self) -> list[Chapter]:
        return self._events(self.clips[0] if len(self.clips) == 1 else None)[0]

    def subtitles(self) -> list[Subtitle]:
        return self._events(self.clips[0] if len(self.clips) == 1 else None)[1]

    def write_text(self, relative: str, text: str) -> Path:
        path = self.take_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.mask(text), encoding="utf-8")
        return path

    def write_outputs(self, summary: dict[str, Any]) -> None:
        """One clip (or none): chapters.txt and subtitles.srt next to video.mp4, as always.
        Several clips: clips/NN-name.chapters.txt and .srt next to each clip's video."""
        clip_reports = []
        if len(self.clips) <= 1:
            chapters, subtitles = self._events(self.clips[0] if self.clips else None)
            if chapters:
                self.write_text("chapters.txt", chapters_txt(chapters))
            if subtitles:
                self.write_text("subtitles.srt", srt(subtitles))
            all_chapters = chapters
        else:
            all_chapters = []
            for clip in self.clips:
                chapters, subtitles = self._events(clip)
                if chapters:
                    self.write_text(f"clips/{clip.stem}.chapters.txt", chapters_txt(chapters))
                if subtitles:
                    self.write_text(f"clips/{clip.stem}.srt", srt(subtitles))
                clip_reports.append({
                    "clip": clip.index, "name": clip.name, "video": clip.video,
                    "chapters": [{"time": round(c.time, 3), "title": c.title}
                                 for c in chapters]})
                all_chapters += chapters
        steps = []
        for rec in self.steps:
            d = asdict(rec)
            # A step is in a clip only if it ran while that clip was recording (unlike a
            # chapter title, which moves on to the next clip).
            clip = next((c for c in self.clips if c.start <= rec.started
                         and (c.end is None or rec.started <= c.end)), None)
            timeline = clip.timeline if clip is not None else self.timeline
            in_video = rec.section == "steps" and (clip is not None or not self.clips)
            d["video_time"] = round(timeline.video_time(rec.started), 3) if in_video else None
            if len(self.clips) > 1:
                d["clip"] = clip.index if clip is not None and in_video else None
            d["started"] = datetime.fromtimestamp(rec.started).isoformat(timespec="milliseconds")
            d["duration"] = round(rec.duration, 3)
            steps.append(d)
        report = {
            **summary,
            "chapters": [{"time": round(c.time, 3), "title": c.title} for c in all_chapters],
            "steps": steps,
        }
        if clip_reports:
            report["clips"] = clip_reports
        self.write_text("report.json", json.dumps(report, indent=2, ensure_ascii=False) + "\n")

    def close(self) -> None:
        self._log.close()
