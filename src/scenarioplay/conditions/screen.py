"""Screen conditions: prompt, text, regex."""

from __future__ import annotations

import re
from typing import Literal

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
        m = re.search(self.regex, joined, re.MULTILINE)
        return m.group(0) if m else None
