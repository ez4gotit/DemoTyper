"""Shared state for one take, handed to every step's execute()."""

from __future__ import annotations

import asyncio
import os
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..conditions.base import Condition, Probe
from ..conditions.combinators import MATCHED_AS
from ..errors import ConsoleLost, StepFailed, WaitTimeout
from ..keystrokes import TypingParams, resolve_typing
from ..lang import ExprError, LiveMapping, Node, Scope, truthy
from ..loader.model import TypingSpec

if TYPE_CHECKING:
    from ..actions.base import Check, StepModel
    from ..console import Console, Session
    from ..loader import ParsedScenario
    from ..recorder import Recorder
    from ..report import Reporter, StepRecord
    from .engine import Engine


@dataclass
class RunOptions:
    record: bool = True
    speed: float = 1.0
    out_dir: Path = Path("takes")
    keep_session: bool = False
    verbose: bool = False
    headless: bool = False
    display: str | None = None
    width: int = 160
    height: int = 45
    typos_rate: float | None = None
    no_typos: bool = False
    secrets_file: Path | None = None
    cli_vars: dict[str, Any] = field(default_factory=dict)       # --var name=value
    vars_file: dict[str, Any] = field(default_factory=dict)      # --vars file.yaml


@dataclass
class TakeInfo:
    id: str
    dir: Path
    started_at: str


@dataclass
class LastResult:
    exit_code: int | None = None
    output: str | None = None
    matched: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


# Setup and finally are not recorded, so they are typed fast.
FAST = TypingSpec(profile="robot")


class RunContext:
    def __init__(self, parsed: ParsedScenario, opts: RunOptions, take: TakeInfo,
                 reporter: Reporter, session: Session, recorder: Recorder,
                 display: str | None):
        self.display = display
        self.parsed = parsed
        self.scenario = parsed.model
        self.defaults = parsed.model.defaults
        self.opts = opts
        self.take = take
        self.reporter = reporter
        self.session = session
        self.recorder = recorder
        self.current = parsed.model.consoles[0].name
        self.section = "steps"
        self.last = LastResult()
        self.record: StepRecord | None = None
        self.executed_mismatches: list[dict[str, str]] = []
        self.secrets: dict[str, str] = {}
        self._typo_notice = False
        self.defines = parsed.defines
        self.call_depth = 0
        self.engine: Engine | None = None
        self.scope = Scope({}, [{}])  # replaced by make_scope() once secrets are known
        from .answers import Responder

        self.responder = Responder(self)

    def make_scope(self, file_vars: dict[str, Any], cli_vars: dict[str, Any],
                   file_overrides: dict[str, Any]) -> None:
        """Variables, lowest priority first (spec 5.1): scenario `vars`, --var, --vars file,
        then values set at run time."""
        last = LiveMapping(lambda: {"exit_code": self.last.exit_code,
                                    "output": self.last.output, "matched": self.last.matched})
        builtins = {
            "env": dict(os.environ),
            "secret": dict(self.secrets),
            "take": {"id": self.take.id, "started_at": self.take.started_at,
                     "dir": str(self.take.dir)},
            "last": last,
        }
        self.scope = Scope(builtins, [dict(file_vars), dict(cli_vars), dict(file_overrides),
                                      {}])

    @property
    def speed(self) -> float:
        return self.opts.speed

    def log(self, level: str, message: str) -> None:
        self.reporter.log(level, message)

    def note(self, message: str) -> None:
        """Log a line and attach it to the current step's record in report.json."""
        self.log("info", message)
        if self.record is not None:
            self.record.notes.append(self.reporter.mask(message))

    # --- consoles and typing -----------------------------------------------------------

    def console_for(self, step: StepModel, name: str | None = None) -> Console:
        return self.session.consoles[name or step.console or self.current]

    def typing_params(self, console: Console, step_spec: TypingSpec | None) -> TypingParams:
        levels = [self.defaults.typing, console.spec.typing, step_spec]
        if self.section != "steps":
            levels.append(FAST)
        return resolve_typing(levels, typos_rate=self.opts.typos_rate,
                              no_typos=self.opts.no_typos)

    def rng(self, key: str, params: TypingParams) -> random.Random:
        """Randomness for one piece of typing; reproducible per key when a seed is set."""
        seed = params.typos.seed
        if seed is None:
            return random.Random()
        return random.Random(f"{seed}:{key}")

    def typo_notice(self) -> None:
        if not self._typo_notice:
            self._typo_notice = True
            self.log("info", "auto-typos are enabled in the scenario but arrive in phase 4; "
                             "this version types without typos")

    async def screenshot(self, path: Path) -> bool:
        if not self.display:
            return False
        from ..recorder import take_screenshot

        return await take_screenshot(self.display, path)

    async def sleep(self, seconds: float, *, scaled: bool = True) -> None:
        if seconds > 0:
            await asyncio.sleep(seconds / self.speed if scaled else seconds)

    # --- steps, variables, checks -----------------------------------------------------

    async def run_steps(self, steps: list[StepModel]) -> None:
        """Run nested steps (for blocks)."""
        assert self.engine is not None
        await self.engine.run_steps(steps)

    async def check(self, check: Check, step: StepModel) -> bool:
        """Evaluate a check once: an expression, or a screen/system condition (spec 8)."""
        if isinstance(check, Node):
            try:
                return truthy(check.eval(self.scope))
            except ExprError as e:
                raise StepFailed(str(e)) from None
        try:
            cond = check.rendered(self.scope)
        except ExprError as e:
            raise StepFailed(str(e)) from None
        console = self.console_for(step, cond.console)
        probe = Probe(console, cond.scope or "since_last_input", {}, self.session.consoles)
        match = await cond.check(probe)
        if match is not None:
            self.last.matched = probe.memo.get(MATCHED_AS) or cond.as_
        return match is not None

    # --- waiting -----------------------------------------------------------------------

    async def wait(self, cond: Condition, step: StepModel, console: Console) -> str | None:
        if cond.console:
            console = self.console_for(step, cond.console)
        timeout = cond.timeout or step.timeout or self.defaults.timeout
        interval = cond.interval or self.defaults.interval
        scope = cond.scope or "since_last_input"
        on_timeout = cond.on_timeout or "fail"
        loop = asyncio.get_running_loop()
        self.log("debug", f"waiting for {cond.describe()} in {console.name!r} "
                          f"(timeout {timeout:g}s)")
        from .answers import AnswerState

        answers = AnswerState()
        memo: dict[Any, Any] = {}
        tries = 2 if on_timeout == "retry" else 1
        for attempt in range(1, tries + 1):
            deadline = loop.time() + timeout
            while True:
                if await self.responder.poll(console, answers):
                    continue
                probe = Probe(console, scope, memo, self.session.consoles)
                match = await cond.check(probe)
                if match is not None:
                    self.last.matched = memo.get(MATCHED_AS) or cond.as_
                    self.log("debug", f"matched {cond.describe()}: {match!r}")
                    return match
                if (await probe.info()).dead:
                    raise ConsoleLost(f"the shell in console {console.name!r} has exited",
                                      expected=cond.describe(), console=console.name)
                if loop.time() >= deadline:
                    break
                await asyncio.sleep(interval)
            message = (f"timed out after {timeout:g}s waiting for {cond.describe()} "
                       f"in console {console.name!r}")
            if attempt < tries:
                self.note(message + "; waiting once more (on_timeout: retry)")
        if on_timeout == "continue":
            self.log("warning", message + " (on_timeout: continue)")
            return None
        if isinstance(on_timeout, list):
            self.note(message + "; running the on_timeout steps")
            await self.run_steps(cond._on_timeout_steps or [])
            return None
        raise WaitTimeout(message, expected=cond.describe(), console=console.name)
