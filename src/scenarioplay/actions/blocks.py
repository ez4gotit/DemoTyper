"""Control blocks (spec 8). Rule: the keyword takes the block's main argument."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from pydantic import Field, NonNegativeFloat, PositiveInt, PrivateAttr

from ..errors import BreakLoop, ContinueLoop, StepAbort, StepFailed, StopTake
from ..plugins import action
from .base import BlockStep, Check, StepModel, render_value

if TYPE_CHECKING:
    from ..engine.context import RunContext
    from ..loader.checks import Checker
    from ..loader.steps import StepParser

IDENT = r"^[A-Za-z_][A-Za-z0-9_]*$"
MAX_CALL_DEPTH = 50


def _loop_vars(index0: int, total: int | None, item: Any = None) -> dict[str, Any]:
    info: dict[str, Any] = {"index": index0 + 1, "index0": index0, "first": index0 == 0}
    if total is not None:
        info.update(length=total, last=index0 == total - 1)
    if item is not None:
        info["item"] = item
    return info


async def _run_body(ctx: RunContext, steps: list[StepModel], scope: dict[str, Any]) -> bool:
    """Run a loop body in its own scope. Returns False when the body did `break`."""
    ctx.scope.push(scope)
    try:
        await ctx.run_steps(steps)
    except ContinueLoop:
        pass
    except BreakLoop:
        return False
    finally:
        ctx.scope.pop()
    return True


@action
class IfBlock(BlockStep):
    """Run `then` if the condition holds; otherwise the first `elif` that holds, or
    `else`. The condition is an expression or a screen/system condition checked once."""

    KEYWORD = "if"
    CHECK_FIELDS = ("if",)
    STEP_LIST_FIELDS = ("then", "else")

    if_: str | dict[str, Any] | bool = Field(alias="if")
    then: list[Any]
    elif_: list[dict[str, Any]] | None = Field(None, alias="elif")
    else_: list[Any] | None = Field(None, alias="else")

    _elifs: list[tuple[Check, list[StepModel]]] = PrivateAttr(default_factory=list)

    @property
    def main(self) -> Any:
        return self.if_

    def parse_extra(self, raw: dict[str, Any], path: tuple[Any, ...],
                    parser: StepParser) -> None:
        for i, item in enumerate(raw.get("elif") or []):
            where = path + ("elif", i)
            if not isinstance(item, dict) or set(item) != {"if", "then"}:
                parser.error("elif: each entry needs exactly `if` and `then`", where)
                continue
            check = parser.parse_check(item["if"], where + ("if",))
            steps = parser.parse_steps(item["then"], where + ("then",))
            if check is not None:
                self._elifs.append((check, steps))

    def children(self):
        yield from super().children()
        for i, (_, steps) in enumerate(self._elifs):
            yield f"elif.{i}", steps

    async def execute(self, ctx: RunContext) -> None:
        if await ctx.check(self.checks["if"], self):
            ctx.note("branch: then")
            await ctx.run_steps(self._children.get("then", []))
            return
        for i, (check, steps) in enumerate(self._elifs):
            if await ctx.check(check, self):
                ctx.note(f"branch: elif {i + 1}")
                await ctx.run_steps(steps)
                return
        if "else" in self._children:
            ctx.note("branch: else")
            await ctx.run_steps(self._children["else"])
        else:
            ctx.note("branch: none")


@action
class ForEachBlock(BlockStep):
    """Repeat the steps for each item of a list (`for_each: [a, b]` or `"{{ var }}"`)."""

    KEYWORD = "for_each"
    IS_LOOP = True
    STEP_LIST_FIELDS = ("steps",)

    for_each: list[Any] | str
    as_: str = Field("item", alias="as", pattern=IDENT)
    steps: list[Any]

    def child_names(self, field: str) -> set[str]:
        return {self.as_, "loop"}

    async def execute(self, ctx: RunContext) -> None:
        items = render_value(self.for_each, ctx.scope, native=True)
        if not isinstance(items, list):
            raise StepFailed(f"for_each needs a list, got {type(items).__name__}: {items!r}")
        for i, item in enumerate(items):
            ctx.note(f"{self.as_} = {item!r} ({i + 1}/{len(items)})")
            scope = {self.as_: item, "loop": _loop_vars(i, len(items), item)}
            if not await _run_body(ctx, self._children["steps"], scope):
                break


@action
class RepeatBlock(BlockStep):
    """Repeat the steps a fixed number of times."""

    KEYWORD = "repeat"
    IS_LOOP = True
    STEP_LIST_FIELDS = ("steps",)

    repeat: PositiveInt | str
    steps: list[Any]

    def child_names(self, field: str) -> set[str]:
        return {"loop"}

    async def execute(self, ctx: RunContext) -> None:
        count = render_value(self.repeat, ctx.scope, native=True)
        try:
            count = int(count)
        except (TypeError, ValueError):
            raise StepFailed(f"repeat needs a number, got {count!r}") from None
        for i in range(count):
            ctx.note(f"repeat {i + 1}/{count}")
            if not await _run_body(ctx, self._children["steps"], {"loop": _loop_vars(i, count)}):
                break


class _ConditionalLoop(BlockStep):
    IS_LOOP = True
    STEP_LIST_FIELDS = ("steps",)

    max_iterations: PositiveInt
    delay: NonNegativeFloat = 0.0
    on_exhausted: Literal["fail", "continue"] = "fail"
    steps: list[Any]

    def child_names(self, field: str) -> set[str]:
        return {"loop"}

    async def _exhausted(self, ctx: RunContext) -> None:
        message = (f"`{self.KEYWORD}` reached max_iterations ({self.max_iterations}) "
                   f"before its condition was met")
        if self.on_exhausted == "continue":
            ctx.log("warning", message + " (on_exhausted: continue)")
            return
        raise StepFailed(message, expected=f"{self.KEYWORD}: {self.main}")


@action
class WhileBlock(_ConditionalLoop):
    """Repeat while the condition holds; it is checked before each pass."""

    KEYWORD = "while"
    CHECK_FIELDS = ("while",)
    while_: str | dict[str, Any] | bool = Field(alias="while")

    @property
    def main(self) -> Any:
        return self.while_

    async def execute(self, ctx: RunContext) -> None:
        for i in range(self.max_iterations):
            if not await ctx.check(self.checks["while"], self):
                return
            ctx.note(f"while: pass {i + 1}")
            if not await _run_body(ctx, self._children["steps"], {"loop": _loop_vars(i, None)}):
                return
            if self.delay:
                await ctx.sleep(self.delay, scaled=False)
        if await ctx.check(self.checks["while"], self):
            await self._exhausted(ctx)


@action
class UntilBlock(_ConditionalLoop):
    """Repeat until the condition holds; it is checked after each pass, so the steps run at
    least once (the condition usually looks at their output)."""

    KEYWORD = "until"
    CHECK_FIELDS = ("until",)
    until: str | dict[str, Any] | bool

    async def execute(self, ctx: RunContext) -> None:
        for i in range(self.max_iterations):
            ctx.note(f"until: pass {i + 1}")
            if not await _run_body(ctx, self._children["steps"], {"loop": _loop_vars(i, None)}):
                return
            if await ctx.check(self.checks["until"], self):
                return
            if self.delay and i < self.max_iterations - 1:
                await ctx.sleep(self.delay, scaled=False)
        await self._exhausted(ctx)


@action
class RetryBlock(BlockStep):
    """Run the steps; if one fails, wait `delay` seconds and run them all again, up to
    `retry` attempts in total."""

    KEYWORD = "retry"
    STEP_LIST_FIELDS = ("steps",)

    retry: PositiveInt
    delay: NonNegativeFloat = 1.0
    on_exhausted: Literal["fail", "continue"] = "fail"
    steps: list[Any]

    async def execute(self, ctx: RunContext) -> None:
        for attempt in range(1, self.retry + 1):
            try:
                await ctx.run_steps(self._children["steps"])
                return
            except StepAbort as e:
                if attempt == self.retry:
                    if self.on_exhausted == "continue":
                        ctx.log("warning", f"retry: all {self.retry} attempts failed; "
                                           "continuing (on_exhausted: continue)")
                        return
                    raise
                ctx.note(f"attempt {attempt}/{self.retry} failed ({e.error}); retrying in "
                         f"{self.delay:g}s")
                await ctx.sleep(self.delay, scaled=False)


@action
class TryBlock(BlockStep):
    """Run `try`; if a step fails, run `catch` (with {{ error.message }} and
    {{ error.step }}) instead of failing. `finally` always runs."""

    KEYWORD = "try"
    STEP_LIST_FIELDS = ("try", "catch", "finally")

    try_: list[Any] = Field(alias="try")
    catch: list[Any] | None = None
    finally_: list[Any] | None = Field(None, alias="finally")

    @property
    def main(self) -> Any:
        return f"{len(self.try_)} steps"

    def child_names(self, field: str) -> set[str]:
        return {"error"} if field == "catch" else set()

    def check(self, checker: Checker) -> None:
        if self.catch is None and self.finally_ is None:
            checker.error(self, "`try` needs `catch`, `finally` or both", "try")

    async def execute(self, ctx: RunContext) -> None:
        try:
            await ctx.run_steps(self._children["try"])
        except StepAbort as e:
            if "catch" not in self._children:
                raise
            error = {"message": ctx.reporter.mask(str(e.error)), "step": e.step.path_str(),
                     "line": e.step.loc.line if e.step.loc else None}
            ctx.note(f"caught: {error['message']}")
            ctx.scope.push({"error": error})
            try:
                await ctx.run_steps(self._children["catch"])
            finally:
                ctx.scope.pop()
        finally:
            if "finally" in self._children:
                await ctx.run_steps(self._children["finally"])


@action
class DefineBlock(BlockStep):
    """Declare a reusable block with parameters; `call` runs it. Defining runs nothing."""

    KEYWORD = "define"
    STEP_LIST_FIELDS = ("steps",)
    NO_RENDER = frozenset({"define"})

    define: str = Field(pattern=IDENT)
    params: list[str] = Field(default_factory=list)
    steps: list[Any]

    def child_names(self, field: str) -> set[str]:
        return set(self.params)

    def check(self, checker: Checker) -> None:
        if len(set(self.params)) != len(self.params):
            checker.error(self, "a parameter is listed twice", "params")

    async def execute(self, ctx: RunContext) -> None:
        return


@action
class CallBlock(BlockStep):
    """Run a `define`d block with parameter values from `with`."""

    KEYWORD = "call"
    NO_RENDER = frozenset({"call"})

    call: str = Field(pattern=IDENT)
    with_: dict[str, Any] = Field(default_factory=dict, alias="with")

    def check(self, checker: Checker) -> None:
        target = checker.defines.get(self.call)
        if target is None:
            known = ", ".join(sorted(checker.defines)) or "none"
            checker.error(self, f"no `define: {self.call}` (defined: {known})", "call")
            return
        missing = set(target.params) - set(self.with_)
        extra = set(self.with_) - set(target.params)
        if missing:
            checker.error(self, f"missing parameter{'s' if len(missing) > 1 else ''} "
                                f"{', '.join(sorted(missing))} for `{self.call}`", "call")
        if extra:
            checker.error(self, f"`{self.call}` has no parameter "
                                f"{', '.join(sorted(extra))}", "with")

    async def execute(self, ctx: RunContext) -> None:
        target = ctx.defines[self.call]
        if ctx.call_depth >= MAX_CALL_DEPTH:
            raise StepFailed(f"calls nested deeper than {MAX_CALL_DEPTH}: is `{self.call}` "
                             "calling itself?")
        values = {k: render_value(v, ctx.scope, native=True) for k, v in self.with_.items()}
        ctx.call_depth += 1
        ctx.scope.push(values)
        try:
            await ctx.run_steps(target._children["steps"])
        finally:
            ctx.scope.pop()
            ctx.call_depth -= 1


@action
class BreakStep(BlockStep):
    """Leave the innermost loop (`break: true`, usually with `when`)."""

    KEYWORD = "break"
    break_: Literal[True] = Field(alias="break")

    @property
    def main(self) -> Any:
        return True

    async def execute(self, ctx: RunContext) -> None:
        raise BreakLoop()


@action
class ContinueStep(BlockStep):
    """Skip to the next pass of the innermost loop (`continue: true`)."""

    KEYWORD = "continue"
    continue_: Literal[True] = Field(alias="continue")

    @property
    def main(self) -> Any:
        return True

    async def execute(self, ctx: RunContext) -> None:
        raise ContinueLoop()


@action
class StopStep(BlockStep):
    """End the take early: `stop: success` or `stop: failure`, with an optional message.
    `finally` still runs."""

    KEYWORD = "stop"
    stop: Literal["success", "failure"]
    message: str | None = None

    async def execute(self, ctx: RunContext) -> None:
        message = render_value(self.message, ctx.scope) if self.message else None
        raise StopTake(self.stop, message)


@action
class IncludeStep(BlockStep):
    """Insert the steps of another file here (a list of steps, or a file with only
    `steps:`). The path is relative to the including file. Resolved when loading."""

    KEYWORD = "include"
    include: str

    async def execute(self, ctx: RunContext) -> None:  # pragma: no cover - never parsed
        raise StepFailed("include is resolved when the scenario loads")
