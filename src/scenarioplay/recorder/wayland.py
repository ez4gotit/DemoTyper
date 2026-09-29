"""Wayland recording with wf-recorder (spec 10.1), for wlroots compositors (Sway, Wayfire,
Hyprland, labwc...). GNOME and KDE on Wayland need the ScreenCast portal, which this version
does not drive; use their Xorg session (the reference setup) or Xvfb.

wf-recorder prints no progress and stamps no wall-clock time, so the first frame's time is
estimated from when capture started (about 0.1-0.3 s off; enough for chapters, which the
spec wants within 0.5 s). It stops cleanly on SIGINT.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from .base import Segment
from .x11 import X11Recorder

STARTUP_GRACE = 0.8  # seconds wf-recorder must stay alive to count as capturing


class WfRecorder(X11Recorder):
    """`display` is a wf-recorder output name (e.g. `eDP-1`), or empty for the default."""

    def argv(self, output: str) -> list[str]:
        argv = ["wf-recorder", "-y", "-f", output, "-c", self.spec.codec,
                "-r", str(self.spec.fps), "-p", f"crf={self.spec.crf}",
                "-p", f"preset={self.spec.preset}", "--pixel-format", "yuv420p"]
        if self.display and not self.display.startswith(":"):
            argv += ["-o", self.display]
        return argv

    async def _start_segment(self, timeout: float = 15.0) -> None:
        output = self._segment_path()
        self._stopping = False
        self._started = False
        started = time.time()
        self.proc = await self.transport.start(self.argv(output),
                                               stderr_path=self.stderr_path, env=self.env)
        self._tasks.append(asyncio.create_task(self._watchdog(self.proc)))
        await asyncio.sleep(STARTUP_GRACE)
        if self.died or self.proc.returncode is not None:
            from ..errors import EnvironmentProblem

            raise EnvironmentProblem(f"wf-recorder exited at start: {await self._stderr_tail()}")
        self._started = True
        self.segments.append(Segment(Path(output), started + 0.2))

    async def _warn_if_black(self) -> None:
        return  # x11grab-based check does not apply

    async def _stop_segment(self) -> None:
        self._stopping = True
        proc = self.proc
        if proc is None or proc.returncode is not None:
            return
        proc.interrupt()
        try:
            await asyncio.wait_for(proc.wait(), 20)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
        if self.segments and self.segments[-1].end is None:
            self.segments[-1].end = time.time()

    async def _probe(self, path: str) -> tuple[float | None, float | None]:
        """No wall-clock timestamps: keep the estimated start; read the length."""
        res = await self.transport.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
             "default=nw=1:nk=1", path])
        try:
            return None, float(res.out.strip())
        except ValueError:
            return None, None

    async def screenshot(self, path: Path,
                         region: tuple[int, int, int, int] | None = None) -> bool:
        path.parent.mkdir(parents=True, exist_ok=True)
        target = str(path) if self.transport.is_local else f"{self.workdir}/{path.name}"
        if region is not None:
            x, y, w, h = region
            where = ["-g", f"{x},{y} {w}x{h}"]
        elif self.display and not self.display.startswith(":"):
            where = ["-o", self.display]
        else:
            where = []
        argv = ["grim", *where, target]
        try:
            res = await self.transport.run(argv, timeout=15, env=self.env)
        except (asyncio.TimeoutError, FileNotFoundError):
            return False
        if res.rc != 0:
            return False
        if not self.transport.is_local:
            await self.transport.fetch(target, str(path))
        return path.exists()
