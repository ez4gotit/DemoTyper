"""Actions that do not type: wait_for, pause, chapter, caption, log, screenshot."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Literal

from pydantic import Field, NonNegativeFloat, PositiveFloat

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
class LogStep(StepModel):
    """Write a line to the take log only."""

    KEYWORD = "log"
    log: str
    level: Literal["debug", "info", "warning", "error"] = "info"

    def check(self, checker: Checker) -> None:
        _no_secret(self, checker, "log", self.log)

    async def execute(self, ctx: RunContext) -> None:
        ctx.log(self.level, self.log)


@action
class ScreenshotStep(StepModel):
    """Save a PNG of the screen into the take's screenshots/ folder."""

    KEYWORD = "screenshot"
    screenshot: str | Literal[True] = True

    def check(self, checker: Checker) -> None:
        if isinstance(self.screenshot, str) and not re.fullmatch(r"[\w.-]+", self.screenshot):
            checker.error(self, "use a plain file name such as `after-install.png`",
                          "screenshot")

    async def execute(self, ctx: RunContext) -> None:
        name = self.screenshot if isinstance(self.screenshot, str) else \
            f"step-{self.path_str().replace('.', '-')}.png"
        if not name.endswith(".png"):
            name += ".png"
        path = ctx.take.dir / "screenshots" / name
        if await ctx.screenshot(path):
            ctx.note(f"screenshot saved: screenshots/{name}")
            return
        # No display (headless run): keep the console text instead.
        console = ctx.console_for(self)
        text = "\n".join(await console.capture())
        ctx.reporter.write_text(f"screenshots/{name[:-4]}.txt", text + "\n")
        ctx.note(f"no display to capture; saved console text as screenshots/{name[:-4]}.txt")
