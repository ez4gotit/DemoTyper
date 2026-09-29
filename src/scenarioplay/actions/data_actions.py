"""Actions that work with data: set, capture, assert, exec (spec 6)."""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING, Any, Literal

from pydantic import Field, PositiveInt

from ..errors import StepFailed
from ..loader.model import Regex, Strict
from ..plugins import action
from .base import StepModel

if TYPE_CHECKING:
    from ..engine.context import RunContext
    from ..loader.checks import Checker

IDENT = r"^[A-Za-z_][A-Za-z0-9_]*$"


class CaptureSpec(Strict):
    """What to keep from some output: a regex (its first group, or the group named in
    `group`) and/or only the last `lines` lines. Without either, the whole text."""

    name: str = Field(pattern=IDENT)
    regex: Regex | None = None
    group: int | str | None = None
    lines: PositiveInt | None = None


def extract(text: str, spec: CaptureSpec) -> str:
    if spec.lines is not None:
        text = "\n".join(text.rstrip("\n").split("\n")[-spec.lines:])
    if spec.regex is None:
        return text.strip()
    try:
        m = re.search(spec.regex, text, re.MULTILINE)
    except re.error as e:
        raise StepFailed(f"invalid regular expression {spec.regex!r}: {e}") from None
    if m is None:
        raise StepFailed(f"capture {spec.name}: {spec.regex!r} did not match the output",
                         expected=f"regex {spec.regex!r}")
    if spec.group is not None:
        try:
            return m.group(spec.group) or ""
        except (IndexError, KeyError):
            raise StepFailed(f"capture {spec.name}: the regex has no group "
                             f"{spec.group!r}") from None
    return (m.group(1) if m.groups() else m.group(0)) or ""


def store(ctx: RunContext, name: str, value: str) -> None:
    ctx.scope.set(name, value)
    shown = value if len(value) <= 60 else value[:57] + "..."
    ctx.note(f"{name} = {shown!r}")


@action
class SetStep(StepModel):
    """Set or change a variable: `set: name` with `value:` (templates keep their type,
    so `value: "{{ packages }}"` stays a list)."""

    KEYWORD = "set"
    NO_RENDER = frozenset({"set"})
    NATIVE = frozenset({"value"})

    set: str = Field(pattern=IDENT)
    value: Any = None

    def summary(self) -> str:
        return f"set: {self.set} = {self.value!r}"

    async def execute(self, ctx: RunContext) -> None:
        ctx.scope.set(self.set, self.value)
        ctx.note(f"{self.set} = {self.value!r}")


@action
class CaptureStep(StepModel):
    """Store output in a variable. `from`: `output` (since the last input, default),
    `screen` (visible screen) or `last_output` (output of the last `run`)."""

    KEYWORD = "capture"
    PRIORITY = 1  # also an option of `run`
    NO_RENDER = frozenset({"capture", "from_"})

    capture: str = Field(pattern=IDENT)
    regex: Regex | None = None
    group: int | str | None = None
    lines: PositiveInt | None = None
    from_: Literal["output", "screen", "last_output"] = Field("output", alias="from")

    async def execute(self, ctx: RunContext) -> None:
        console = ctx.console_for(self)
        if self.from_ == "last_output":
            text = ctx.last.output or ""
        elif self.from_ == "screen" or console.output_start is None:
            text = "\n".join(await console.capture())
        else:
            # Output since the last input, without the shell prompt that followed it.
            text = await console.command_output()
        spec = CaptureSpec(name=self.capture, regex=self.regex, group=self.group,
                           lines=self.lines)
        store(ctx, self.capture, extract(text, spec))


@action
class AssertStep(StepModel):
    """Fail if the condition is false: an expression, or a screen/system condition."""

    KEYWORD = "assert"
    CHECK_FIELDS = ("assert",)

    assert_: str | dict[str, Any] | bool = Field(alias="assert")
    message: str | None = None

    @property
    def main(self) -> Any:
        return self.assert_

    async def execute(self, ctx: RunContext) -> None:
        if not await ctx.check(self.checks["assert"], self):
            raise StepFailed(self.message or f"assertion failed: {self.assert_}",
                             expected=str(self.assert_))


@action
class ExecStep(StepModel):
    """Run a command out of view (not typed on screen), e.g. for checks. Sets
    {{ last.exit_code }} and {{ last.output }}; `capture: name` stores its output."""

    KEYWORD = "exec"
    NO_RENDER = frozenset({"capture"})

    exec: str
    capture: str | None = Field(None, pattern=IDENT)
    check_exit: bool = False
    cwd: str | None = None

    async def execute(self, ctx: RunContext) -> None:
        console = ctx.console_for(self)
        timeout = self.timeout or ctx.defaults.timeout
        try:
            # On the console's machine: the target, or the console's `host`.
            res = await console.run_out_of_view(self.exec, cwd=self.cwd, timeout=timeout)
        except asyncio.TimeoutError:
            raise StepFailed(f"exec: `{self.exec}` did not finish within {timeout:g}s") \
                from None
        output = res.out.rstrip("\n")
        ctx.last.exit_code = res.rc
        ctx.last.output = output
        ctx.log("info", f"exec exit code {res.rc}" + (f": {output[-200:]}" if output else ""))
        if self.capture:
            store(ctx, self.capture, output.strip())
        if self.check_exit and res.rc != 0:
            raise StepFailed(f"exec: `{self.exec}` exited with code {res.rc}: "
                             f"{res.err.strip()[-300:]}", exit_code=res.rc,
                             expected="exit code 0")

    def check(self, checker: Checker) -> None:
        if not self.exec.strip():
            checker.error(self, "the command is empty", "exec")
