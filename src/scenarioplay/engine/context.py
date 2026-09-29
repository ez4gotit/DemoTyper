"""Shared state for one take, handed to every step's execute()."""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..conditions.base import Condition, Probe
from ..errors import ConsoleLost, WaitTimeout
from ..keystrokes import TypingParams, resolve_typing
from ..loader.model import TypingSpec

if TYPE_CHECKING:
    from ..actions.base import StepModel
    from ..console import Console, Session
    from ..loader import ParsedScenario
    from ..recorder import Recorder
    from ..report import Reporter, StepRecord


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
        from .answers import Responder

        self.responder = Responder(self)

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

    # --- waiting -----------------------------------------------------------------------

    async def wait(self, cond: Condition, step: StepModel, console: Console) -> str | None:
        if cond.console:
            console = self.console_for(step, cond.console)
        timeout = cond.timeout or step.timeout or self.defaults.timeout
        interval = cond.interval or self.defaults.interval
        scope = cond.scope or "since_last_input"
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        self.log("debug", f"waiting for {cond.describe()} in {console.name!r} "
                          f"(timeout {timeout:g}s)")
        from .answers import AnswerState

        answers = AnswerState()
        while True:
            if await self.responder.poll(console, answers):
                continue
            probe = Probe(console, scope)
            match = await cond.check(probe)
            if match is not None:
                self.last.matched = cond.as_
                self.log("debug", f"matched {cond.describe()}: {match!r}")
                return match
            if (await probe.info()).dead:
                raise ConsoleLost(f"the shell in console {console.name!r} has exited",
                                  expected=cond.describe(), console=console.name)
            if loop.time() >= deadline:
                message = (f"timed out after {timeout:g}s waiting for {cond.describe()} "
                           f"in console {console.name!r}")
                if (cond.on_timeout or "fail") == "continue":
                    self.log("warning", message + " (on_timeout: continue)")
                    return None
                raise WaitTimeout(message, expected=cond.describe(), console=console.name)
            await asyncio.sleep(interval)
