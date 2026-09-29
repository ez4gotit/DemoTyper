"""Walks the step tree (spec 8): `when`, template rendering, `on_fail` policies."""

from __future__ import annotations

import asyncio
import sys
import time
from typing import TYPE_CHECKING

from ..errors import ControlSignal, StepAbort, StepFailed, StopTake
from ..lang import ExprError
from ..loader.model import OnFailRetry
from ..report import StepRecord

if TYPE_CHECKING:
    from ..actions.base import StepModel
    from .context import RunContext


def _read_answer(prompt: str) -> str:
    sys.stderr.write(prompt)
    sys.stderr.flush()
    line = sys.stdin.readline()
    if not line:
        raise EOFError
    return line


class Engine:
    def __init__(self, ctx: RunContext):
        self.ctx = ctx
        ctx.engine = self

    async def run_section(self, name: str, steps: list[StepModel]) -> None:
        self.ctx.section = name
        await self.run_steps(steps)

    async def run_steps(self, steps: list[StepModel]) -> None:
        for step in steps:
            await self.run_step(step)

    async def run_step(self, step: StepModel) -> None:
        ctx = self.ctx
        record = StepRecord(
            path=step.path_str(), section=ctx.section, action=step.KEYWORD,
            summary=step.summary(), label=step.label,
            line=step.loc.line if step.loc else None, started=time.time())
        ctx.reporter.step_started(record)
        parent, ctx.record = ctx.record, record
        loop = asyncio.get_running_loop()
        began = loop.time()
        try:
            when = step.checks.get("when")
            if when is not None and not await ctx.check(when, step):
                record.status = "skipped"
                ctx.log("info", "  skipped (`when` is false)")
                return
            if ctx.opts.step_mode and ctx.section == "steps" and not step.IS_BLOCK \
                    and not await self._ask(step):
                record.status = "skipped"
                ctx.log("info", "  skipped at the --step prompt")
                return
            await self._run_with_policy(step, record)
        except ControlSignal:
            record.status = "ok"
            raise
        except asyncio.CancelledError:
            record.status = "interrupted"
            raise
        finally:
            record.duration = loop.time() - began
            ctx.record = parent

    async def _run_with_policy(self, step: StepModel, record: StepRecord) -> None:
        ctx = self.ctx
        policy = step.on_fail if step.on_fail is not None else ctx.defaults.on_fail
        attempts = policy.retry + 1 if isinstance(policy, OnFailRetry) else 1
        for attempt in range(1, attempts + 1):
            try:
                await self._execute(step)
                record.status = "ok"
                return
            except (StepFailed, StepAbort) as e:
                error = e.error if isinstance(e, StepAbort) else e
                if attempt < attempts:
                    assert isinstance(policy, OnFailRetry)
                    ctx.note(f"attempt {attempt}/{attempts} failed ({error}); retrying in "
                             f"{policy.delay:g}s")
                    await ctx.sleep(policy.delay, scaled=False)
                    continue
                record.error = ctx.reporter.mask(str(error))
                if policy == "continue":
                    record.status = "failed-continued"
                    ctx.log("warning", f"step {record.path} failed, continuing (on_fail: "
                                       f"continue): {error}")
                    return
                if step._on_fail_steps is not None:
                    record.status = "recovered"
                    ctx.note(f"failed ({error}); running the on_fail steps")
                    await self.run_steps(step._on_fail_steps)
                    return
                record.status = "failed"
                if isinstance(e, StepAbort):
                    raise  # a nested step failed; its evidence stays with it
                ctx.log("error", f"step {record.path} failed: {error}")
                raise StepAbort(step, error) from e

    async def _ask(self, step: StepModel) -> bool:
        """`run --step`: wait for the operator before each step. Enter runs it, `s` skips
        it, `c` runs the rest without asking, `q` stops the take."""
        where = f" (line {step.loc.line})" if step.loc else ""
        prompt = (f"\nnext: {step.path_str()} {step.summary()}{where}\n"
                  "  [Enter] run  [s] skip  [c] continue without asking  [q] quit > ")
        loop = asyncio.get_running_loop()
        try:
            answer = await loop.run_in_executor(None, _read_answer, prompt)
        except EOFError:
            answer = ""
        answer = answer.strip().lower()
        if answer == "q":
            raise StopTake("interrupted", "stopped at a --step prompt")
        if answer == "c":
            self.ctx.opts.step_mode = False
        return answer != "s"

    async def _execute(self, step: StepModel) -> None:
        ctx = self.ctx
        try:
            target = step if step.IS_BLOCK else step.rendered(ctx.scope)
        except ExprError as e:
            raise StepFailed(f"cannot fill in variables: {e}") from None
        try:
            await target.execute(ctx)
        except ExprError as e:
            raise StepFailed(str(e)) from None
