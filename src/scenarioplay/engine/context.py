"""Shared state for one take, handed to every step's execute()."""

from __future__ import annotations

import asyncio
import os
import random
import re
from contextvars import ContextVar
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
    from_name: str | None = None      # --from: label or chapter
    to_name: str | None = None        # --to
    step_mode: bool = False           # --step: ask before each step
    burn_subtitles: bool = False      # --burn-subtitles
    cast: bool = False                # --cast: asciinema file per console
    target_kind: str | None = None    # --target: overrides target.kind


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
        self.section = "steps"
        self.executed_mismatches: list[dict[str, str]] = []
        self.secrets: dict[str, str] = {}
        self.paused_at: float | None = None  # when `record: pause` ran
        self.vm: Any = None  # the VMwareTarget, for `vm` steps
        self.restart_guest: Any = None  # Take.restart_guest (revert/reboot + rebuild)
        # Set by the take: record: start/stop, and screenshots (name, console, text).
        self.start_clip: Any = None
        self.stop_clip: Any = None
        self.grab_screenshot: Any = None
        self.chapter_count = 0
        self.chapter_title: str | None = None
        self.defines = parsed.defines
        self.engine: Engine | None = None
        # Per-task state: each `parallel` branch runs in its own asyncio task and gets its
        # own current console, step record, variable scope (loop variables) and last.*.
        self._current: ContextVar[str] = ContextVar("current")
        self._record: ContextVar[StepRecord | None] = ContextVar("record", default=None)
        self._scope: ContextVar[Scope] = ContextVar("scope")
        self._last: ContextVar[LastResult] = ContextVar("last")
        self._depth: ContextVar[int] = ContextVar("call_depth", default=0)
        self._in_parallel: ContextVar[bool] = ContextVar("in_parallel", default=False)
        self._current.set(parsed.model.consoles[0].name)
        self._scope.set(Scope({}, [{}]))  # replaced by make_scope() once secrets are known
        self._last.set(LastResult())
        from .answers import Responder

        self.responder = Responder(self)

    # --- per-task state ----------------------------------------------------------------

    @property
    def current(self) -> str:
        return self._current.get()

    @current.setter
    def current(self, name: str) -> None:
        self._current.set(name)

    @property
    def record(self) -> StepRecord | None:
        return self._record.get()

    @record.setter
    def record(self, value: StepRecord | None) -> None:
        self._record.set(value)

    @property
    def scope(self) -> Scope:
        return self._scope.get()

    @property
    def last(self) -> LastResult:
        return self._last.get()

    @property
    def call_depth(self) -> int:
        return self._depth.get()

    @call_depth.setter
    def call_depth(self, value: int) -> None:
        self._depth.set(value)

    @property
    def in_parallel(self) -> bool:
        return self._in_parallel.get()

    def enter_branch(self, console: str) -> None:
        """Called at the start of a `parallel` branch's task (its own context copy)."""
        self._current.set(console)
        self._scope.set(self.scope.fork())
        self._last.set(LastResult(**{k: getattr(self.last, k)
                                     for k in ("exit_code", "output", "matched")}))
        self._in_parallel.set(True)

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
        self._scope.set(Scope(builtins, [dict(file_vars), dict(cli_vars), dict(file_overrides),
                                         {}]))

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
        name = name or step.console or self.current
        console = self.session.consoles.get(name)
        if console is None:
            state = "closed" if name in self.session.closed else "not open yet"
            raise StepFailed(f"console {name!r} is {state}; open it with `open_console`")
        return console

    async def activate(self, console: Console) -> None:
        """Before input: show and highlight this console (spec 9.2). In parallel branches
        split-layout panes stay as they are, so two consoles can be typed into at once."""
        if self.in_parallel and not self.session.windowed:
            return
        if await self.session.activate(console):
            await self.sleep(0.35)  # let the viewer's eye follow the switch

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


    async def screenshot(self, name: str, console: Console | None = None,
                         text: bool | None = None) -> list[str]:
        """Save screenshots/<name>.png (and the text, if asked); returns the files saved."""
        if self.grab_screenshot is None:
            return []
        return await self.grab_screenshot(name, console, text)

    # --- chapters and automatic screenshots ------------------------------------------

    async def begin_chapter(self, title: str) -> None:
        """Called by `chapter` steps: automatic screenshots at chapter boundaries."""
        mode = self.defaults.screenshots.chapters
        if mode in ("end", "both") and self.chapter_title is not None:
            await self._chapter_shot("end")
        self.chapter_count += 1
        self.chapter_title = title
        if mode in ("start", "both"):
            await self._chapter_shot("start")

    async def end_of_steps(self) -> None:
        if self.defaults.screenshots.chapters in ("end", "both") and self.chapter_title:
            await self._chapter_shot("end")

    async def _chapter_shot(self, when: str) -> None:
        slug = re.sub(r"[^A-Za-z0-9]+", "-", self.chapter_title or "").strip("-").lower()[:40]
        name = f"{self.chapter_count:02d}-{slug or 'chapter'}-{when}"
        saved = await self.screenshot(name)
        if saved:
            self.log("info", f"screenshot at chapter {when}: {', '.join(saved)}")

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
