"""Recorder interface and the timeline that maps wall-clock time to video time."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path


class Timeline:
    """Maps wall-clock timestamps (time.time()) to positions in the video.

    t0 is the wall-clock time of the first video frame. Until the recorder knows it, t0 is
    the moment the recorded part of the take began.
    """

    def __init__(self) -> None:
        self.t0: float | None = None

    def video_time(self, wall: float) -> float:
        if self.t0 is None:
            return 0.0
        return max(0.0, wall - self.t0)


class Recorder:
    """Base class. Subclasses capture the screen between start() and stop()."""

    video_path: Path | None = None

    def __init__(self) -> None:
        self.died = False
        self.on_death: Callable[[], None] | None = None

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def finalize(self, keep: bool) -> Path | None:
        """Turn the raw capture into video.mp4. Returns its path, or None."""
        return None

    def frame0_wall(self) -> float | None:
        """Wall-clock time of the first frame, if known."""
        return None

    async def screenshot(self, path: Path) -> bool:
        return False


class NullRecorder(Recorder):
    """Used with --no-record."""
