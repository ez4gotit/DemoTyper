"""Multiple consoles (spec 9): use, focus, open_console, close_console, parallel."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Literal

from pydantic import PrivateAttr

from ..errors import StepAbort
from ..plugins import action
from .base import BlockStep, StepModel

if TYPE_CHECKING:
    from ..engine.context import RunContext
    from ..loader.checks import Checker
    from ..loader.steps import StepParser


def _check_name(step: StepModel, checker: Checker, name: str, field: str) -> None:
    checker.check_console(step, name, field)


@action
class UseStep(StepModel):
    """Make a console the current one: later steps without `console:` run there."""

    KEYWORD = "use"
    NO_RENDER = frozenset({"use"})
    use: str

    def check(self, checker: Checker) -> None:
        _check_name(self, checker, self.use, "use")

    async def execute(self, ctx: RunContext) -> None:
        ctx.console_for(self, self.use)  # fails clearly if closed
        ctx.current = self.use


@action
class FocusStep(StepModel):
    """Bring a console to the front and highlight it. `zoom: true` makes its pane fill the
    screen for readability; `zoom: false` restores the layout."""

    KEYWORD = "focus"
    NO_RENDER = frozenset({"focus"})
    focus: str
    zoom: bool | None = None

    def check(self, checker: Checker) -> None:
        _check_name(self, checker, self.focus, "focus")
        if self.zoom and checker.scenario.layout not in ("split-horizontal", "split-vertical",
                                                         "grid"):
            checker.warning(self, "zoom only changes split layouts; with one console per "
                                  "window the console is already full screen", "zoom")

    async def execute(self, ctx: RunContext) -> None:
        console = ctx.console_for(self, self.focus)
        if self.zoom is None:
            await ctx.session.activate(console)
        else:
            await ctx.session.zoom(console, self.zoom)
        await ctx.sleep(0.3)


@action
class OpenConsoleStep(StepModel):
    """Open a declared console mid-take (one with `start: false`, or one closed earlier)."""

    KEYWORD = "open_console"
    NO_RENDER = frozenset({"open_console"})
    open_console: str

    def check(self, checker: Checker) -> None:
        _check_name(self, checker, self.open_console, "open_console")

    async def execute(self, ctx: RunContext) -> None:
        await ctx.session.open_console(self.open_console, self.timeout or 20.0)
        ctx.note(f"opened console {self.open_console!r}")


@action
class CloseConsoleStep(StepModel):
    """Close a console mid-take; its text still goes into the transcript."""

    KEYWORD = "close_console"
    NO_RENDER = frozenset({"close_console"})
    close_console: str

    def check(self, checker: Checker) -> None:
        _check_name(self, checker, self.close_console, "close_console")

    async def execute(self, ctx: RunContext) -> None:
        await ctx.session.close_console(self.close_console)
        if ctx.current == self.close_console:
            ctx.current = next(iter(ctx.session.consoles))
        ctx.note(f"closed console {self.close_console!r}")


@action
class ParallelBlock(BlockStep):
    """Run branches at the same time, one console per branch (spec 9.3).

    `wait: all` (default) ends when every branch is done; `wait: any` ends when the first
    branch is done and stops the others. A failing branch stops the others and fails the
    block."""

    KEYWORD = "parallel"
    parallel: list[dict[str, Any]]
    wait: Literal["all", "any"] = "all"

    _branches: list[tuple[str, list[StepModel]]] = PrivateAttr(default_factory=list)

    @property
    def main(self) -> Any:
        return ", ".join(name for name, _ in self._branches) or f"{len(self.parallel)} branches"

    def summary(self) -> str:
        return f"parallel ({self.wait}): {self.main}"

    def parse_extra(self, raw: dict[str, Any], path: tuple[Any, ...],
                    parser: StepParser) -> None:
        for i, item in enumerate(raw.get("parallel") or []):
            where = path + ("parallel", i)
            if not isinstance(item, dict) or set(item) != {"console", "steps"} \
                    or not isinstance(item.get("console"), str):
                parser.error("parallel: each branch needs exactly `console` (a name) and "
                             "`steps`", where)
                continue
            self._branches.append((item["console"],
                                   parser.parse_steps(item["steps"], where + ("steps",))))

    def children(self):
        yield from super().children()
        for i, (name, steps) in enumerate(self._branches):
            yield f"branch.{i}:{name}", steps

    def check(self, checker: Checker) -> None:
        from ..loader.steps import walk

        if not self.parallel:
            checker.error(self, "`parallel` needs at least one branch", "parallel")
        names = [name for name, _ in self._branches]
        for name in names:
            _check_name(self, checker, name, "parallel")
        dupes = sorted({n for n in names if names.count(n) > 1})
        if dupes:
            checker.error(self, f"two branches use console {dupes[0]!r}; each branch needs its "
                                "own console", "parallel")
        if self.console is not None:
            checker.error(self, "`console` goes on each branch, not on `parallel`", "console")
        for name, steps in self._branches:
            for step in walk(steps):
                if step.console is not None and step.console != name:
                    checker.error(step, f"inside the parallel branch for {name!r}, steps run "
                                        f"in that console; `console: {step.console}` would "
                                        "race with another branch", "console")

    async def execute(self, ctx: RunContext) -> None:
        async def run_branch(index: int, console: str, steps: list[StepModel]) -> int:
            ctx.enter_branch(console)  # this task's own context copy
            ctx.console_for(self, console)
            await ctx.run_steps(steps)
            return index

        tasks = [asyncio.create_task(run_branch(i, name, steps), name=f"parallel:{name}")
                 for i, (name, steps) in enumerate(self._branches)]
        try:
            mode = asyncio.FIRST_COMPLETED if self.wait == "any" else asyncio.FIRST_EXCEPTION
            done, pending = await asyncio.wait(tasks, return_when=mode)
            for task in done:
                if task.exception() is not None:
                    raise task.exception()  # type: ignore[misc]
            if self.wait == "any" and pending:
                first = next(iter(done)).result()
                others = ", ".join(t.get_name().split(":", 1)[1] for t in pending)
                ctx.note(f"branch {self._branches[first][0]!r} finished first; stopping "
                         f"{others}")
        except StepAbort:
            ctx.note("a branch failed; stopping the others")
            raise
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
