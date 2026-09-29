"""Writes the take folder (spec section 10.2): log, chapters, subtitles, report, transcripts."""

from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO

import click

from ..recorder.base import Timeline
from .formats import Chapter, Subtitle, chapters_txt, srt
from .masker import Masker

LEVELS = {"debug": 10, "info": 20, "warning": 30, "error": 40}
CHAPTER_SUBTITLE_SECONDS = 4.0


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

    def chapters(self) -> list[Chapter]:
        vt = self.timeline.video_time
        return [Chapter(vt(w), t, c) for w, t, c in self._chapters]

    def subtitles(self) -> list[Subtitle]:
        vt = self.timeline.video_time
        subs = []
        for wall, title, caption in self._chapters:
            text = title + (f"\n{caption}" if caption else "")
            subs.append(Subtitle(vt(wall), vt(wall) + CHAPTER_SUBTITLE_SECONDS, text))
        for wall, text, duration in self._captions:
            subs.append(Subtitle(vt(wall), vt(wall) + duration, text))
        return subs

    def write_text(self, relative: str, text: str) -> Path:
        path = self.take_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.mask(text), encoding="utf-8")
        return path

    def write_outputs(self, summary: dict[str, Any]) -> None:
        chapters = self.chapters()
        if chapters:
            self.write_text("chapters.txt", chapters_txt(chapters))
        subtitles = self.subtitles()
        if subtitles:
            self.write_text("subtitles.srt", srt(subtitles))
        vt = self.timeline.video_time
        steps = []
        for rec in self.steps:
            d = asdict(rec)
            d["video_time"] = round(vt(rec.started), 3) if rec.section == "steps" else None
            d["started"] = datetime.fromtimestamp(rec.started).isoformat(timespec="milliseconds")
            d["duration"] = round(rec.duration, 3)
            steps.append(d)
        report = {
            **summary,
            "chapters": [{"time": round(c.time, 3), "title": c.title} for c in chapters],
            "steps": steps,
        }
        self.write_text("report.json", json.dumps(report, indent=2, ensure_ascii=False) + "\n")

    def close(self) -> None:
        self._log.close()
