"""Recorder interface and the timeline that maps wall-clock time to video time."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Segment:
    """One continuous piece of video. `record: pause` ends one; `resume` starts the next."""

    path: Path
    start: float  # wall-clock time of the first frame (estimated, exact after finalize)
    end: float | None = None  # wall-clock time the capture stopped
    duration: float | None = None  # exact length of the file, after finalize


class Timeline:
    """Maps wall-clock timestamps (time.time()) to positions in the final video.

    Without segments (no recording), t0 is the moment the recorded part began. With
    segments, time spent while recording was paused maps to the point where it paused.
    """

    def __init__(self) -> None:
        self._t0: float | None = None
        self.segments: list[Segment] = []

    @property
    def t0(self) -> float | None:
        return self.segments[0].start if self.segments else self._t0

    @t0.setter
    def t0(self, value: float | None) -> None:
        self._t0 = value

    def video_time(self, wall: float) -> float:
        if not self.segments:
            return 0.0 if self._t0 is None else max(0.0, wall - self._t0)
        offset = 0.0
        for seg in self.segments:
            if wall < seg.start:
                return offset  # while paused: the point where the video resumes
            if seg.duration is not None:
                length = seg.duration
            elif seg.end is not None:
                length = seg.end - seg.start
            else:
                return offset + (wall - seg.start)
            if wall <= seg.start + length:
                return offset + (wall - seg.start)
            offset += length
        return offset


class Recorder:
    """Base class. Subclasses capture the screen between start() and stop()."""

    video_path: Path | None = None

    def __init__(self) -> None:
        self.died = False
        self.on_death: Callable[[], None] | None = None
        self.segments: list[Segment] = []
        self.paused = False

    async def start(self) -> None: ...

    async def pause(self) -> None: ...

    async def resume(self) -> None: ...

    async def stop(self) -> None: ...

    async def finalize(self, keep: bool) -> Path | None:
        """Turn the raw capture into video.mp4. Returns its path, or None."""
        return None

    def frame0_wall(self) -> float | None:
        """Wall-clock time of the first frame, if known."""
        return self.segments[0].start if self.segments else None

    async def screenshot(self, path: Path) -> bool:
        return False


class NullRecorder(Recorder):
    """Used with --no-record."""
