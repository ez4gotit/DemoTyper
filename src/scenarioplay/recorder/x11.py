"""Screen recording with ffmpeg x11grab (spec section 10.1).

The capture is written to a Matroska file first, which stays playable if ffmpeg or the
runner is killed, and remuxed to MP4 at the end. `-copyts` keeps x11grab's wall-clock
frame timestamps, so the first frame's time is read back exactly with ffprobe.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from pathlib import Path

from ..errors import EnvironmentProblem
from ..loader.model import RecorderSpec
from ..transport.local import clean_env
from .base import Recorder

Log = Callable[[str, str], None]


def _grab_input(spec: RecorderSpec, display: str) -> list[str]:
    return ["-f", "x11grab", "-framerate", str(spec.fps),
            "-draw_mouse", "1" if spec.draw_mouse else "0", "-i", display]


async def take_screenshot(display: str, path: Path) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "x11grab",
        "-draw_mouse", "0", "-i", display, "-frames:v", "1", str(path),
        stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL, env=clean_env())
    try:
        rc = await asyncio.wait_for(proc.wait(), 15)
    except asyncio.TimeoutError:
        proc.kill()
        return False
    return rc == 0 and path.exists()


BLACK_WARNING = (
    "the captured screen is entirely black, so the video will be too. On WSLg and other "
    "Wayland desktops the X display is XWayland, whose root window x11grab sees as black: "
    "record on an Xorg session or under Xvfb instead")


async def screen_is_black(display: str) -> bool | None:
    """Grab one frame and check whether every pixel is (near) black. None if it failed."""
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "x11grab", "-draw_mouse", "0",
        "-i", display, "-frames:v", "1", "-vf", "format=gray", "-f", "rawvideo", "-",
        stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL, env=clean_env())
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), 15)
    except asyncio.TimeoutError:
        return None
    finally:
        if proc.returncode is None:  # timed out or cancelled: do not leave it behind
            proc.kill()
            await proc.wait()
    if proc.returncode != 0 or not out:
        return None
    return max(out) < 24


class X11Recorder(Recorder):
    def __init__(self, spec: RecorderSpec, display: str, take_dir: Path, log: Log):
        super().__init__()
        self.spec = spec
        self.display = display
        self.take_dir = take_dir
        self.log = log
        self.raw_path = take_dir / "video.mkv"
        self.video_path = take_dir / "video.mp4"
        self.stderr_path = take_dir / "recorder.log"
        self.proc: asyncio.subprocess.Process | None = None
        self._capturing = asyncio.Event()
        self._started = False
        # Until finalize() reads the first frame's exact timestamp from the file, this stands
        # in for it: the first progress report, which arrives 0.05-0.15 s after the first
        # frame (measured, warm and cold start; launch time is off by seconds when cold).
        self._t0_estimate: float | None = None
        self._t0_exact: float | None = None
        self._stopping = False
        self._tasks: list[asyncio.Task[None]] = []

    def argv(self) -> list[str]:
        return ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                *_grab_input(self.spec, self.display),
                "-vf", "crop=trunc(iw/2)*2:trunc(ih/2)*2",
                "-c:v", self.spec.codec, "-preset", self.spec.preset,
                "-crf", str(self.spec.crf), "-pix_fmt", "yuv420p",
                "-copyts", "-progress", "pipe:1", "-stats_period", "0.1", "-nostats",
                str(self.raw_path)]

    async def start(self, timeout: float = 15.0) -> None:
        self.take_dir.mkdir(parents=True, exist_ok=True)
        stderr = open(self.stderr_path, "wb")
        try:
            self.proc = await asyncio.create_subprocess_exec(
                *self.argv(), stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=stderr, env=clean_env())
        except FileNotFoundError:
            raise EnvironmentProblem("ffmpeg is not installed") from None
        finally:
            stderr.close()
        self._tasks = [asyncio.create_task(self._read_progress()),
                       asyncio.create_task(self._watchdog())]
        try:
            await asyncio.wait_for(self._capturing.wait(), timeout)
        except asyncio.TimeoutError:
            await self.stop()
            raise EnvironmentProblem(
                f"ffmpeg did not start capturing display {self.display} within {timeout:.0f}s:"
                f" {self._stderr_tail()}") from None
        if self.died:
            raise EnvironmentProblem(f"ffmpeg exited at start: {self._stderr_tail()}")
        self._started = True
        self.log("info", f"recording display {self.display} to {self.raw_path.name}")
        # In the background: a full-frame grab can take seconds on a cold start, and
        # waiting for it would stretch the lead-in.
        self._tasks.append(asyncio.create_task(self._warn_if_black()))

    async def _warn_if_black(self) -> None:
        if await screen_is_black(self.display):
            self.log("warning", BLACK_WARNING)

    async def _read_progress(self) -> None:
        assert self.proc and self.proc.stdout
        block: dict[str, str] = {}
        while True:
            line = await self.proc.stdout.readline()
            if not line:
                break
            key, _, value = line.decode(errors="replace").strip().partition("=")
            block[key] = value
            if key != "progress":
                continue
            # Any progress report means the display opened and capture runs (a display that
            # cannot be opened makes ffmpeg exit before its first report). Frame counts are
            # useless here: x264 buffers ~1.5 s of frames before the first one is counted.
            if not self._capturing.is_set():
                self._t0_estimate = time.time() - 0.1
                self._capturing.set()
            block = {}

    async def _watchdog(self) -> None:
        assert self.proc
        await self.proc.wait()
        if not self._stopping:
            self.died = True
            self._capturing.set()
            if self._started:  # during start(), start() itself reports the failure
                self.log("error", f"the recorder exited unexpectedly: {self._stderr_tail()}")
                if self.on_death:
                    self.on_death()

    def _stderr_tail(self) -> str:
        try:
            text = self.stderr_path.read_text(errors="replace").strip()
        except OSError:
            return "(no output)"
        return text.splitlines()[-1] if text else "(no output)"

    async def stop(self) -> None:
        self._stopping = True
        proc = self.proc
        if proc is None or proc.returncode is not None:
            return
        try:
            assert proc.stdin
            proc.stdin.write(b"q")
            await proc.stdin.drain()
            proc.stdin.close()
        except (BrokenPipeError, ConnectionResetError):
            pass
        try:
            await asyncio.wait_for(proc.wait(), 20)
        except asyncio.TimeoutError:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), 5)
            except asyncio.TimeoutError:
                proc.kill()
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    def frame0_wall(self) -> float | None:
        return self._t0_exact or self._t0_estimate

    async def _probe_start_time(self) -> float | None:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "error", "-show_entries", "format=start_time", "-of",
            "default=nw=1:nk=1", str(self.raw_path), stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL, env=clean_env())
        out, _ = await proc.communicate()
        try:
            value = float(out.decode().strip())
        except ValueError:
            return None
        # x11grab stamps frames with wall-clock time; anything else means we cannot use it.
        return value if value > 1e9 else None

    async def finalize(self, keep: bool) -> Path | None:
        if not self.raw_path.exists():
            return None
        if not keep:
            self.raw_path.unlink(missing_ok=True)
            return None
        exact = await self._probe_start_time()
        if exact is not None:
            self._t0_exact = exact
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(self.raw_path),
            "-c", "copy", "-movflags", "+faststart", str(self.video_path),
            stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE, env=clean_env())
        _, err = await proc.communicate()
        if proc.returncode == 0 and self.video_path.exists():
            self.raw_path.unlink(missing_ok=True)
            return self.video_path
        self.log("warning", f"could not convert the video to MP4, kept {self.raw_path.name}: "
                            f"{err.decode(errors='replace').strip()[-300:]}")
        return self.raw_path

    async def screenshot(self, path: Path) -> bool:
        return await take_screenshot(self.display, path)
