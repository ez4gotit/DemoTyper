"""any / all: combine conditions (spec 7.1). With `any`, the matching branch's `as` name
is stored in {{ last.matched }}."""

from __future__ import annotations

from typing import Any

from ..plugins import condition
from .base import Condition, Probe

MATCHED_AS = "matched_as"


@condition
class AnyCondition(Condition):
    """Holds as soon as one of the conditions holds. Each may name a `console`."""

    KEYWORD = "any"
    any: list[Any]

    def describe(self) -> str:
        return "any of: " + "; ".join(c.describe() for c in self.children)

    async def check(self, probe: Probe) -> str | None:
        for child in self.children:
            match = await child.check(probe.for_console(child.console))
            if match is not None:
                probe.memo[MATCHED_AS] = child.as_
                return match
        return None


@condition
class AllCondition(Condition):
    """Holds when every condition holds in the same poll."""

    KEYWORD = "all"
    all: list[Any]

    def describe(self) -> str:
        return "all of: " + "; ".join(c.describe() for c in self.children)

    async def check(self, probe: Probe) -> str | None:
        matches = []
        for child in self.children:
            match = await child.check(probe.for_console(child.console))
            if match is None:
                return None
            matches.append(match)
        return "; ".join(matches)
