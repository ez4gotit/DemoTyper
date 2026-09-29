"""Wait conditions (spec section 7): the base class and the per-poll screen probe."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, Literal

from pydantic import Field, PositiveFloat, PrivateAttr

from ..lang import Env
from ..loader.model import Strict

if TYPE_CHECKING:
    from ..console.driver import Console, PaneInfo, ShellStatus
    from ..transport import Result

Scope = Literal["since_last_input", "screen"]


class Probe:
    """One poll of one console. Caches tmux calls so several checks share them.

    `memo` lives for the whole wait (all polls), for conditions that need history such as
    `idle`. `for_console` gives a probe of another console in the same poll.
    """

    def __init__(self, console: Console, scope: Scope, memo: dict[Any, Any] | None = None,
                 consoles: dict[str, Console] | None = None):
        self.console = console
        self.scope = scope
        self.memo = memo if memo is not None else {}
        self.consoles = consoles or {console.name: console}
        self._others: dict[str, Probe] = {}
        self._info: PaneInfo | None = None
        self._screen: list[str] | None = None
        self._output: list[str] | None = None
        self._status: ShellStatus | bool | None = False

    def for_console(self, name: str | None) -> Probe:
        if name is None or name == self.console.name:
            return self
        if name not in self._others:
            self._others[name] = Probe(self.consoles[name], self.scope, self.memo,
                                       self.consoles)
        return self._others[name]

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

    async def run(self, command: str, timeout: float = 30.0) -> Result:
        """Run a shell command out of view on the console's machine, in its directory."""
        return await self.console.run_out_of_view(command, timeout=timeout)


class Condition(Strict):
    """Base class for wait conditions. Subclasses set KEYWORD and implement check()."""

    KEYWORD: ClassVar[str] = ""
    # False for conditions that only make sense while waiting (such as `idle`).
    SINGLE_SHOT: ClassVar[bool] = True
    # Fields that are names or settings, not text to render.
    NO_RENDER: ClassVar[frozenset[str]] = frozenset(
        {"scope", "on_timeout", "console", "as_", "timeout", "interval"})

    timeout: PositiveFloat | None = None
    interval: PositiveFloat | None = None
    scope: Scope | None = None
    on_timeout: Literal["fail", "continue", "retry"] | list[Any] | None = None
    console: str | None = None
    as_: str | None = Field(None, alias="as")

    _on_timeout_steps: list[Any] | None = PrivateAttr(default=None)
    _children: list[Condition] = PrivateAttr(default_factory=list)

    @property
    def children(self) -> list[Condition]:
        return self._children

    def describe(self) -> str:
        value = getattr(self, self.KEYWORD)
        return f"{self.KEYWORD} {value!r}"

    def rendered(self, env: Env) -> Condition:
        from ..actions.base import render_value

        updates = {}
        for name in type(self).model_fields:
            if name in self.NO_RENDER:
                continue
            value = getattr(self, name)
            new = render_value(value, env)
            if new is not value:
                updates[name] = new
        copy = self.model_copy(update=updates)
        copy._children = [c.rendered(env) for c in self._children]
        return copy

    async def check(self, probe: Probe) -> str | None:
        """Return a short description of the match, or None if the condition does not hold."""
        raise NotImplementedError
