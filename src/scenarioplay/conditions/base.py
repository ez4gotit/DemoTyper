"""Wait conditions (spec section 7): the base class and the per-poll screen probe."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Literal

from pydantic import Field, PositiveFloat

from ..loader.model import Strict

if TYPE_CHECKING:
    from ..console.driver import Console, PaneInfo, ShellStatus

Scope = Literal["since_last_input", "screen"]


class Probe:
    """One poll of one console. Caches tmux calls so several checks share them."""

    def __init__(self, console: Console, scope: Scope):
        self.console = console
        self.scope = scope
        self._info: PaneInfo | None = None
        self._screen: list[str] | None = None
        self._output: list[str] | None = None
        self._status: ShellStatus | bool | None = False

    async def info(self) -> PaneInfo:
        if self._info is None:
            self._info = await self.console.info()
        return self._info

    async def screen(self) -> list[str]:
        """Visible lines of the pane, wrapped lines joined."""
        if self._screen is None:
            self._screen = await self.console.capture()
        return self._screen

    async def output(self) -> list[str]:
        """Lines produced after the last input (or the whole screen, per scope)."""
        if self._output is None:
            start = self.console.output_start
            if self.scope == "screen" or start is None:
                self._output = await self.screen()
            else:
                self._output = await self.console.capture(start_abs=start)
        return self._output

    async def status(self) -> ShellStatus | None:
        if self._status is False:
            self._status = await self.console.status()
        return self._status  # type: ignore[return-value]


class Condition(Strict):
    """Base class for wait conditions. Subclasses set KEYWORD and implement check()."""

    KEYWORD: ClassVar[str] = ""

    timeout: PositiveFloat | None = None
    interval: PositiveFloat | None = None
    scope: Scope | None = None
    on_timeout: Literal["fail", "continue"] | None = None
    console: str | None = None
    as_: str | None = Field(None, alias="as")

    def describe(self) -> str:
        value = getattr(self, self.KEYWORD)
        return f"{self.KEYWORD} {value!r}"

    async def check(self, probe: Probe) -> str | None:
        """Return a short description of the match, or None if the condition does not hold."""
        raise NotImplementedError
