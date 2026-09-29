"""Screen recording with ffmpeg x11grab (spec section 10.1).

Each segment is captured to a Matroska file, which stays playable if ffmpeg or the runner
is killed. `-copyts` keeps x11grab's wall-clock frame timestamps, so each segment's first
frame time is read back exactly with ffprobe. `record: pause` ends a segment and
`record: resume` starts the next; finalize() joins them into video.mp4.

ffmpeg runs through the transport, so the same recorder works on this machine or inside a
VMware guest over SSH (recording mode A); files are then fetched into the take folder.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Callable
from pathlib import Path

from ..errors import EnvironmentProblem
from ..loader.model import RecorderSpec
from ..transport import LocalTransport, Transport
from ..transport.base import Process
from .base import Recorder, Segment

Log = Callable[[str, str], None]

BLACK_WARNING = (
    "the captured screen is entirely black, so the video will be too. On WSLg and other "
    "Wayland desktops the X display is XWayland, whose root window x11grab sees as black: "
    "record on an Xorg session or under Xvfb instead")


def _grab_input(spec: RecorderSpec, display: str) -> list[str]:
    return ["-f", "x11grab", "-framerate", str(spec.fps),
            "-draw_mouse", "1" if spec.draw_mouse else "0", "-i", display]


async def screen_is_black(display: str, transport: Transport | None = None,
                          env: dict[str, str] | None = None) -> bool | None:
    """Grab one frame and check whether every pixel is (near) black. None if it failed."""
    transport = transport or LocalTransport()
    try:
        res = await transport.run(
            ["ffmpeg", "-hide_banner", "-f", "x11grab", "-draw_mouse", "0", "-i", display,
             "-frames:v", "1", "-vf", "signalstats,metadata=print:key=lavfi.signalstats.YMAX",
             "-f", "null", "-"], timeout=15, env=env)
    except (asyncio.TimeoutError, FileNotFoundError):
        return None
    m = re.search(r"lavfi\.signalstats\.YMAX=(\d+)", res.err + res.out)
    if res.rc != 0 or not m:
        return None
    return int(m.group(1)) < 24


async def take_screenshot(display: str, path: Path, transport: Transport | None = None,
                          workdir: str | None = None,
                          env: dict[str, str] | None = None) -> bool:
    transport = transport or LocalTransport()
    path.parent.mkdir(parents=True, exist_ok=True)
    target = str(path) if transport.is_local else f"{workdir}/{path.name}"
    try:
        res = await transport.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "x11grab",
             "-draw_mouse", "0", "-i", display, "-frames:v", "1", target], timeout=15,
            env=env)
    except (asyncio.TimeoutError, FileNotFoundError):
        return False
    if res.rc != 0:
        return False
    if not transport.is_local:
        await transport.fetch(target, str(path))
    return path.exists()


class X11Recorder(Recorder):
    def __init__(self, spec: RecorderSpec, display: str, take_dir: Path, log: Log,
                 transport: Transport | None = None, workdir: str | None = None,
                 env: dict[str, str] | None = None):
        super().__init__()
        self.env = env or {}  # DISPLAY/XAUTHORITY for a guest's X server
        self.spec = spec
        self.display = display
        self.take_dir = take_dir
        self.log = log
        self.transport = transport or LocalTransport()
        # Where ffmpeg writes: the take folder here, or a directory on the guest.
        self.workdir = str(take_dir) if self.transport.is_local else (workdir or "/tmp")
        self.video_path = take_dir / "video.mp4"
        self.stderr_path = f"{self.workdir}/recorder.log"
        self.proc: Process | None = None
        self._capturing = asyncio.Event()
        self._started = False
        self._stopping = False
        self._tasks: list[asyncio.Task[None]] = []

    @property
    def raw_path(self) -> Path:
        """The first segment (kept for callers that expect one file)."""
        return Path(f"{self.workdir}/video.mkv")

    def _segment_path(self) -> str:
        n = len(self.segments) + 1
        return f"{self.workdir}/video.mkv" if n == 1 else f"{self.workdir}/video.part{n}.mkv"

    def argv(self, output: str) -> list[str]:
        return ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                *self.grab_input(),
                "-vf", "crop=trunc(iw/2)*2:trunc(ih/2)*2",
                "-c:v", self.spec.codec, "-preset", self.spec.preset,
                "-crf", str(self.spec.crf), "-pix_fmt", "yuv420p",
                "-copyts", "-progress", "pipe:1", "-stats_period", "0.1", "-nostats", output]

    def grab_input(self) -> list[str]:
        return _grab_input(self.spec, self.display)

    # --- segments ----------------------------------------------------------------------

    async def start(self, timeout: float = 15.0) -> None:
        self.take_dir.mkdir(parents=True, exist_ok=True)
        await self._start_segment(timeout)
        self.log("info", f"recording display {self.display}")
        # In the background: a full-frame grab can take seconds on a cold start, and
        # waiting for it would stretch the lead-in.
        self._tasks.append(asyncio.create_task(self._warn_if_black()))

    async def _start_segment(self, timeout: float = 15.0) -> None:
        output = self._segment_path()
        self._capturing = asyncio.Event()
        self._stopping = False
        self._started = False
        try:
            self.proc = await self.transport.start(self.argv(output),
                                                   stderr_path=self.stderr_path, env=self.env)
        except FileNotFoundError:
            raise EnvironmentProblem("ffmpeg is not installed") from None
        estimate: list[float] = []
        self._tasks += [asyncio.create_task(self._read_progress(self.proc, estimate)),
                        asyncio.create_task(self._watchdog(self.proc))]
        try:
            await asyncio.wait_for(self._capturing.wait(), timeout)
        except asyncio.TimeoutError:
            await self._stop_segment()
            raise EnvironmentProblem(
                f"ffmpeg did not start capturing display {self.display} within {timeout:.0f}s:"
                f" {await self._stderr_tail()}") from None
        if self.died:
            raise EnvironmentProblem(f"ffmpeg exited at start: {await self._stderr_tail()}")
        self._started = True
        self.segments.append(Segment(Path(output), estimate[0] if estimate else time.time()))

    async def _read_progress(self, proc: Process, estimate: list[float]) -> None:
        while True:
            line = await proc.readline()
            if not line:
                break
            if not line.startswith(b"progress="):
                continue
            # Any progress report means the display opened and capture runs (a display that
            # cannot be opened makes ffmpeg exit before its first report). Frame counts are
            # useless here: x264 buffers ~1.5 s of frames before the first one is counted.
            # The first report arrives 0.05-0.15 s after the first frame (measured, warm and
            # cold starts); finalize() replaces this estimate with the exact time.
            if not self._capturing.is_set():
                estimate.append(time.time() - 0.1)
                self._capturing.set()

    async def _watchdog(self, proc: Process) -> None:
        await proc.wait()
        if not self._stopping:
            self.died = True
            self._capturing.set()
            if self._started:  # during start(), start() itself reports the failure
                self.log("error", "the recorder exited unexpectedly: "
                                  f"{await self._stderr_tail()}")
                if self.on_death:
                    self.on_death()

    async def _warn_if_black(self) -> None:
        if await screen_is_black(self.display, self.transport, self.env):
            self.log("warning", BLACK_WARNING)

    async def _stderr_tail(self) -> str:
        text = (await self.transport.read_file(self.stderr_path) or "").strip()
        return text.splitlines()[-1] if text else "(no output)"

    async def _stop_segment(self) -> None:
        self._stopping = True
        proc = self.proc
        if proc is None or proc.returncode is not None:
            return
        try:
            await proc.write(b"q")
            await proc.close_stdin()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        try:
            await asyncio.wait_for(proc.wait(), 20)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
        if self.segments and self.segments[-1].end is None:
            self.segments[-1].end = time.time()

    async def pause(self) -> None:
        if self.paused or not self.segments:
            return
        await self._stop_segment()
        self.paused = True
        self.log("info", f"recording paused after segment {len(self.segments)}")

    async def resume(self) -> None:
        if not self.paused:
            return
        await self._start_segment()
        self.paused = False
        self.log("info", f"recording resumed (segment {len(self.segments)})")

    async def stop(self) -> None:
        await self._stop_segment()
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []

    # --- after recording ---------------------------------------------------------------

    async def _probe(self, path: str) -> tuple[float | None, float | None]:
        """(start_time, duration) of a segment. With -copyts the container's duration is
        the absolute end time, so the length is end minus start."""
        res = await self.transport.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=start_time,duration", "-of",
             "default=nw=1", path])
        values = dict(line.split("=", 1) for line in res.out.split() if "=" in line)
        try:
            start = float(values["start_time"])
            end = float(values["duration"])
        except (KeyError, ValueError):
            return None, None
        # x11grab stamps frames with wall-clock time; anything else means we cannot use it.
        if start < 1e9:
            return None, None
        return start, max(0.0, end - start) if end > start else None

    async def finalize(self, keep: bool) -> Path | None:
        existing = [s for s in self.segments if await self.transport.exists(str(s.path))]
        if not existing:
            return None
        if not keep:
            for s in existing:
                await self.transport.remove_file(str(s.path))
            return None
        for seg in existing:
            start, duration = await self._probe(str(seg.path))
            if start is not None:
                seg.start = start
            if duration is not None:
                seg.duration = duration
        output = f"{self.workdir}/video.mp4"
        if len(existing) == 1:
            argv = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i",
                    str(existing[0].path), "-c", "copy", "-movflags", "+faststart", output]
        else:
            listing = f"{self.workdir}/segments.txt"
            await self.transport.write_file(
                listing, "".join(f"file '{s.path}'\n" for s in existing))
            argv = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat",
                    "-safe", "0", "-i", listing, "-c", "copy", "-movflags", "+faststart",
                    output]
        res = await self.transport.run(argv, timeout=600)
        if res.rc == 0 and await self.transport.exists(output):
            if not self.transport.is_local:
                await self.transport.fetch(output, str(self.video_path))
            for s in existing:
                await self.transport.remove_file(str(s.path))
            if len(existing) > 1:
                await self.transport.remove_file(f"{self.workdir}/segments.txt")
            return self.video_path
        self.log("warning", "could not convert the video to MP4, kept the .mkv segments: "
                            f"{res.err.strip()[-300:]}")
        kept = []
        for s in existing:
            local = self.take_dir / s.path.name
            if not self.transport.is_local:
                await self.transport.fetch(str(s.path), str(local))
            kept.append(local)
        return kept[0]

    async def screenshot(self, path: Path) -> bool:
        return await take_screenshot(self.display, path, self.transport, self.workdir,
                                     self.env)
