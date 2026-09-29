"""Screen conditions: prompt, text, regex."""

from __future__ import annotations

import re
import time
from typing import Literal

from pydantic import PositiveFloat

from ..errors import StepFailed
from ..loader.model import Regex
from ..plugins import condition
from .base import Condition, Probe


def last_nonempty(lines: list[str]) -> str | None:
    for line in reversed(lines):
        if line.strip():
            return line
    return None


@condition
class PromptCondition(Condition):
    """The console's prompt is back: the prompt regex matches the last non-empty line and,
    when the hidden shell hook is active, the shell has finished a command since the last
    input."""

    KEYWORD = "prompt"
    prompt: Literal[True] = True

    def describe(self) -> str:
        return "the shell prompt"

    async def check(self, probe: Probe) -> str | None:
        console = probe.console
        line = last_nonempty(await probe.screen())
        if line is None or not console.prompt_matches(line):
            return None
        if console.hook_ok and console.enter_seq is not None:
            status = await probe.status()
            if status is None or status.seq <= console.enter_seq:
                return None
        return line.strip()


@condition
class TextCondition(Condition):
    """This exact text appears in the output."""

    KEYWORD = "text"
    text: str

    async def check(self, probe: Probe) -> str | None:
        joined = "\n".join(await probe.output())
        return self.text if self.text in joined else None


@condition
class RegexCondition(Condition):
    """This regular expression matches the output (multi-line mode: ^ and $ match per line)."""

    KEYWORD = "regex"
    regex: Regex

    async def check(self, probe: Probe) -> str | None:
        joined = "\n".join(await probe.output())
        try:
            m = re.search(self.regex, joined, re.MULTILINE)
        except re.error as e:  # only possible after template rendering
            raise StepFailed(f"invalid regular expression {self.regex!r}: {e}") from None
        return m.group(0) if m else None


@condition
class GoneCondition(Condition):
    """This text is no longer visible (a progress bar or spinner ended). Like `text`, it
    looks at the output since the last input, so the typed command itself does not count;
    `scope: screen` looks at the whole screen."""

    KEYWORD = "gone"
    gone: str

    async def check(self, probe: Probe) -> str | None:
        return None if self.gone in "\n".join(await probe.output()) else f"{self.gone!r} gone"


@condition
class IdleCondition(Condition):
    """The screen has not changed for this many seconds (for programs without a prompt)."""

    KEYWORD = "idle"
    SINGLE_SHOT = False
    idle: PositiveFloat

    def describe(self) -> str:
        return f"the screen to stay still for {self.idle:g}s"

    async def check(self, probe: Probe) -> str | None:
        info = await probe.info()
        snapshot = hash(("\n".join(await probe.screen()), info.cursor_x, info.cursor_y))
        now = time.monotonic()
        key = ("idle", id(self), probe.console.name)
        last = probe.memo.get(key)
        if last is None or last[0] != snapshot:
            probe.memo[key] = (snapshot, now)
            return None
        still = now - last[1]
        return f"still for {still:.1f}s" if still >= self.idle else None
