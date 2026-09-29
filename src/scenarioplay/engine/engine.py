"""Walks the step tree. Phase 1 has flat step lists; blocks arrive in phase 2."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from ..errors import StepAbort, StepFailed
from ..report import StepRecord

if TYPE_CHECKING:
    from ..actions.base import StepModel
    from .context import RunContext


class Engine:
    def __init__(self, ctx: RunContext):
        self.ctx = ctx

    async def run_section(self, name: str, steps: list[StepModel]) -> None:
        self.ctx.section = name
        for step in steps:
            await self.run_step(step)

    async def run_step(self, step: StepModel) -> None:
        ctx = self.ctx
        record = StepRecord(
            path=step.path_str(), section=ctx.section, action=step.KEYWORD,
            summary=step.summary(), label=step.label,
            line=step.loc.line if step.loc else None, started=time.time())
        ctx.reporter.step_started(record)
        ctx.record = record
        loop = asyncio.get_running_loop()
        began = loop.time()
        try:
            await step.execute(ctx)
            record.status = "ok"
        except StepFailed as e:
            record.error = ctx.reporter.mask(str(e))
            policy = step.on_fail or ctx.defaults.on_fail
            if policy == "continue":
                record.status = "failed-continued"
                ctx.log("warning", f"step {record.path} failed, continuing (on_fail: "
                                   f"continue): {e}")
                return
            record.status = "failed"
            ctx.log("error", f"step {record.path} failed: {e}")
            raise StepAbort(step, e) from e
        except asyncio.CancelledError:
            record.status = "interrupted"
            raise
        finally:
            record.duration = loop.time() - began
            ctx.record = None
