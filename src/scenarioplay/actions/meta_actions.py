"""Actions that do not type: wait_for, pause, chapter, caption, log, screenshot."""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING, Any, Literal

from pydantic import Field, NonNegativeFloat, PositiveFloat

from ..loader.model import Strict
from ..plugins import action
from .base import StepModel

_SECRET_REF = re.compile(r"\{\{\s*secret\.")


def _no_secret(step: StepModel, checker: Checker, field: str, text: str | None) -> None:
    """Spec 12: a secret must never be put into a caption, chapter or log line."""
    if text and _SECRET_REF.search(text):
        checker.error(step, "secrets cannot be shown in captions, chapters or logs", field)

if TYPE_CHECKING:
    from ..engine.context import RunContext
    from ..loader.checks import Checker


@action
class WaitForStep(StepModel):
    """Block until a screen condition holds (spec section 7)."""

    KEYWORD = "wait_for"
    PRIORITY = 2  # also an option of input steps
    CONDITION_FIELDS = ("wait_for",)
    wait_for: dict[str, Any] | str

    def summary(self) -> str:
        cond = self.conditions.get("wait_for")
        return f"wait_for: {cond.describe() if cond else self.wait_for}"

    async def execute(self, ctx: RunContext) -> None:
        await ctx.wait(self.conditions["wait_for"], self, ctx.console_for(self))


@action
class PauseStep(StepModel):
    """Wait a fixed number of seconds so the viewer can read (scaled by --speed)."""

    KEYWORD = "pause"
    pause: NonNegativeFloat

    async def execute(self, ctx: RunContext) -> None:
        await ctx.sleep(self.pause)


@action
class ChapterStep(StepModel):
    """Start a chapter: video chapter marker, subtitle and log section."""

    KEYWORD = "chapter"
    chapter: str = Field(min_length=1)
    caption: str | None = None

    def check(self, checker: Checker) -> None:
        _no_secret(self, checker, "chapter", self.chapter)
        _no_secret(self, checker, "caption", self.caption)

    async def execute(self, ctx: RunContext) -> None:
        if ctx.section == "steps":
            await ctx.begin_chapter(self.chapter)  # automatic screenshots, if configured
            ctx.reporter.chapter(self.chapter, self.caption)
        else:
            ctx.log("info", f"=== {ctx.section}: {self.chapter} (not recorded)")


@action
class CaptionStep(StepModel):
    """Show a subtitle line for some seconds without starting a chapter."""

    KEYWORD = "caption"
    PRIORITY = 1  # also an option of `chapter`
    caption: str = Field(min_length=1)
    duration: PositiveFloat = 4.0

    def check(self, checker: Checker) -> None:
        _no_secret(self, checker, "caption", self.caption)

    async def execute(self, ctx: RunContext) -> None:
        if ctx.section == "steps":
            ctx.reporter.caption(self.caption, self.duration)


@action
class RecordStep(StepModel):
    """Control the video at any point.

    `pause` / `resume` cut a stretch out of the current video (e.g. a long download); on
    resume a caption says how much time was skipped. `stop` / `start` end the current video
    file and begin a new one: a take with several clips writes clips/NN-name.mp4, each with
    its own chapters and subtitles. With `target.recorder.autostart: false`, nothing is
    recorded until the first `record: start`."""

    KEYWORD = "record"
    record: Literal["pause", "resume", "start", "stop"]
    caption: bool = Field(True, description="On resume: add a subtitle saying how much time "
                                            "was skipped.")
    clip: str | None = Field(None, description="On start: a name for the new clip (used in "
                                               "its file name).")

    def check(self, checker: Checker) -> None:
        if self.clip is not None and self.record != "start":
            checker.error(self, "`clip` names a clip on `record: start`", "clip")

    async def execute(self, ctx: RunContext) -> None:
        recorder = ctx.recorder
        if ctx.section != "steps":
            ctx.log("info", f"record: {self.record} ignored outside `steps` (not recorded)")
            return
        if not ctx.opts.record:
            ctx.note(f"record: {self.record} (not recording in this take)")
            return
        if self.record == "start":
            if await ctx.start_clip(self.clip):
                ctx.note(f"recording started: clip {len(ctx.reporter.clips)}"
                         + (f" ({self.clip})" if self.clip else ""))
            else:
                ctx.log("warning", "record: start, but a clip is already recording")
            return
        if self.record == "stop":
            if await ctx.stop_clip():
                ctx.note(f"recording stopped: clip {len(ctx.reporter.clips)} ends here")
            else:
                ctx.log("warning", "record: stop, but nothing is recording")
            return
        if not recorder.segments:
            ctx.log("warning", f"record: {self.record}, but nothing is recording")
            return
        if self.record == "pause":
            if recorder.paused:
                ctx.log("warning", "record: pause, but the recording is already paused")
                return
            await recorder.pause()
            ctx.paused_at = time.time()
            ctx.note("recording paused")
            return
        if not recorder.paused:
            ctx.log("warning", "record: resume, but the recording is not paused")
            return
        await recorder.resume()
        skipped = time.time() - (ctx.paused_at or time.time())
        ctx.note(f"recording resumed; {skipped:.0f} s skipped")
        if self.caption:
            ctx.reporter.caption(f"({_duration(skipped)} skipped)", 3.0)


def _duration(seconds: float) -> str:
    seconds = round(seconds)
    if seconds < 60:
        return f"{seconds} s"
    return f"{seconds // 60} min {seconds % 60:02d} s"


@action
class LogStep(StepModel):
    """Write a line to the take log only."""

    KEYWORD = "log"
    log: str
    level: Literal["debug", "info", "warning", "error"] = "info"

    def check(self, checker: Checker) -> None:
        _no_secret(self, checker, "log", self.log)

    async def execute(self, ctx: RunContext) -> None:
        ctx.log(self.level, self.log)


class ScreenshotSpec(Strict):
    """`screenshot: {file: x.png, console: logs, text: true}`"""

    file: str | None = Field(None, description="File name (default: named after the step).")
    console: str | None = Field(None, description="Crop the picture to this console's pane.")
    text: bool | None = Field(None, description="Also save the console text as .html (with "
                                                "colours) and .txt.")


@action
class ScreenshotStep(StepModel):
    """Save a PNG of the screen into the take's screenshots/ folder. It works while
    recording, while recording is stopped, and with --no-record. With `console` it crops to
    that console's pane; with `text` it also saves the console text (HTML with colours, and
    plain text). A headless take has no screen, so it saves the text only."""

    KEYWORD = "screenshot"
    screenshot: str | Literal[True] | ScreenshotSpec = True
    text: bool | None = Field(None, description="Also save the console text as .html and "
                                                ".txt (default: defaults.screenshots.text).")

    def summary(self) -> str:
        spec = self._spec()
        parts = [spec.file or "(named after the step)"]
        if spec.console or self.console:
            parts.append(f"console {spec.console or self.console}")
        return "screenshot: " + ", ".join(parts)

    def _spec(self) -> ScreenshotSpec:
        if isinstance(self.screenshot, ScreenshotSpec):
            return self.screenshot
        return ScreenshotSpec(file=self.screenshot if isinstance(self.screenshot, str)
                              else None)

    def check(self, checker: Checker) -> None:
        spec = self._spec()
        if spec.file is not None and not re.fullmatch(r"[\w.-]+", spec.file):
            checker.error(self, "use a plain file name such as `after-install.png`",
                          "screenshot")
        checker.check_console(self, spec.console, "screenshot")
        if spec.console and self.console and spec.console != self.console:
            checker.error(self, "give the console once: `console:` or inside `screenshot:`",
                          "console")

    async def execute(self, ctx: RunContext) -> None:
        spec = self._spec()
        name = spec.file or f"step-{self.path_str().replace('.', '-')}"
        crop = spec.console or self.console
        console = ctx.console_for(self, crop) if crop else None
        text = spec.text if spec.text is not None else self.text
        saved = await ctx.screenshot(name, console, text)
        if saved:
            ctx.note("screenshot saved: " + ", ".join(saved))
        else:
            ctx.log("warning", "screenshot: nothing could be saved")
