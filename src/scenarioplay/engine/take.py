"""One take from start to finish (spec sections 3.4, 10, 12).

Order: prepare the target, create consoles and the terminal window, run `setup` (not
recorded), start recording, lead-in, `steps`, tail, stop recording, run `finally`, write
the take folder, clean up.
"""

from __future__ import annotations

import asyncio
import io
import os
import re
import secrets
import signal
import sys
import tempfile
import time
import traceback
from datetime import datetime
from typing import Any

from ruamel.yaml import YAML

from ..console import Session
from ..console.session import SESSION
from ..console.terminal import TerminalWindow
from ..errors import ControlSignal, EnvironmentProblem, StepAbort, StopTake
from ..exitcodes import ExitCode
from ..loader import ParsedScenario
from ..loader.load import resolve_includes
from ..recorder import NullRecorder, Recorder, X11Recorder, take_screenshot
from ..report import Reporter
from ..secretstore import load_secrets, referenced_secrets
from ..transport import LocalTransport
from .context import RunContext, RunOptions, TakeInfo
from .engine import Engine


def slug(text: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return s[:40] or "take"


class Take:
    def __init__(self, parsed: ParsedScenario, opts: RunOptions):
        self.parsed = parsed
        self.opts = opts
        now = datetime.now()
        self.id = f"{now:%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"
        self.dir = opts.out_dir / f"{slug(parsed.title)}-{self.id}"
        self.info = TakeInfo(self.id, self.dir, now.isoformat(timespec="seconds"))
        self.reporter = Reporter(self.dir, verbose=opts.verbose)
        target = parsed.model.target
        self.display = opts.display or target.recorder.display or os.environ.get("DISPLAY")
        self.headless = opts.headless or (not opts.record and not self.display)
        self.recorder: Recorder = NullRecorder()
        self.recording = False
        self.session: Session | None = None
        self.terminal: TerminalWindow | None = None
        self.ctx: RunContext | None = None
        self.engine: Engine | None = None
        self.runtime_dir = os.path.join(
            os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir(), f"scenarioplay-{self.id}")
        self.status = "success"
        self.exit = ExitCode.OK
        self.failure: dict[str, Any] | None = None
        self.initial_vars: dict[str, Any] | None = None
        self._interrupted = False
        self._task: asyncio.Task[Any] | None = None

    def log(self, level: str, message: str) -> None:
        self.reporter.log(level, message)

    # --- the take ------------------------------------------------------------------------

    async def run(self) -> int:
        self._task = asyncio.current_task()
        loop = asyncio.get_running_loop()
        try:
            loop.add_signal_handler(signal.SIGINT, self._on_sigint)
        except (NotImplementedError, RuntimeError):
            pass
        self.log("info", f"take {self.id}: {self.parsed.file} -> {self.dir}")
        try:
            await self._play()
        except StopTake as e:
            if e.status == "success":
                self.log("info", f"stopped early: {e}")
            else:
                self.status, self.exit = "failed", ExitCode.STEP_FAILED
                self.failure = {"error": self.reporter.mask(str(e))}
                self.log("error", f"stopped: {e}")
        except StepAbort as e:
            self.status, self.exit = "failed", ExitCode.STEP_FAILED
            await self._collect_evidence(e)
        except EnvironmentProblem as e:
            self.status, self.exit = "error", ExitCode.ENVIRONMENT
            self.failure = {"error": str(e)}
            self.log("error", str(e))
        except asyncio.CancelledError:
            if self._task is not None and hasattr(self._task, "uncancel"):
                self._task.uncancel()
            if self.recorder.died:
                self.status, self.exit = "failed", ExitCode.ENVIRONMENT
                self.failure = {"error": "the screen recorder stopped unexpectedly"}
            else:
                self.status, self.exit = "interrupted", ExitCode.INTERRUPTED
                self.failure = {"error": "interrupted by the user"}
        except Exception as e:  # a bug: still finish the video and the log
            self.status, self.exit = "error", ExitCode.ENVIRONMENT
            self.failure = {"error": f"internal error: {e!r}"}
            self.log("error", "internal error:\n" + traceback.format_exc())
        try:
            await self._wrap_up()
        finally:
            try:
                loop.remove_signal_handler(signal.SIGINT)
            except (NotImplementedError, RuntimeError):
                pass
            self.reporter.close()
        return int(self.exit)

    def _on_sigint(self) -> None:
        if self._interrupted:
            return
        self._interrupted = True
        self.log("warning", "interrupted (Ctrl+C): stopping and finishing the video")
        if self._task:
            self._task.cancel()

    async def _play(self) -> None:
        parsed, opts = self.parsed, self.opts
        target = parsed.model.target
        if sys.platform != "linux":
            raise EnvironmentProblem("the local target runs on the Linux machine itself; run "
                                     "scenarioplay there (for example in WSL)")
        if target.kind != "local":
            raise EnvironmentProblem("the vmware target is planned for phase 4")
        if opts.record and not self.display:
            raise EnvironmentProblem("no X display to record ($DISPLAY is not set); pass "
                                     "--display, or rehearse with --no-record")
        # Resolve secrets before touching anything, so a missing one costs nothing.
        secret_values = load_secrets(referenced_secrets(parsed), opts.secrets_file, self.log)
        for value in secret_values.values():
            self.reporter.mask.register(value)
        if secret_values:
            self.log("info", f"secrets loaded: {', '.join(sorted(secret_values))}")

        transport = LocalTransport()
        self.session = Session(transport, self.runtime_dir, self.id, self.log)
        await self.session.create(parsed.model, opts.width, opts.height)
        if not self.headless:
            assert self.display
            attach = self.session.tmux.argv("attach-session", "-t", SESSION)
            self.terminal = TerminalWindow(target.terminal, attach, self.display)
            await self.terminal.open()
            await self.session.wait_attached()
        else:
            self.log("info", "headless: no terminal window (attach with: "
                             f"tmux -L {self.session.tmux.socket} attach)")
        await self.session.wait_ready()

        self.ctx = RunContext(parsed, opts, self.info, self.reporter, self.session,
                              self.recorder, None if self.headless else self.display)
        self.ctx.secrets = secret_values
        self.ctx.make_scope(parsed.model.vars, opts.cli_vars, opts.vars_file)
        self.initial_vars = self.ctx.scope.snapshot()
        self.engine = Engine(self.ctx)

        setup = parsed.sections.get("setup", [])
        if setup:
            self.log("info", "--- setup (not recorded)")
            await self.engine.run_section("setup", setup)
            if parsed.model.defaults.clear_after_setup:
                await self.session.clear()

        if opts.record:
            assert self.display
            recorder = X11Recorder(target.recorder, self.display, self.dir, self.log)
            recorder.on_death = self._task.cancel if self._task else None
            self.recorder = recorder
            self.ctx.recorder = recorder
            await recorder.start()
            self.recording = True
        self.reporter.timeline.t0 = self.recorder.frame0_wall() or time.time()
        if self.recording:
            # The lead-in counts from the first frame, which ffmpeg captured a moment
            # before it reported it.
            elapsed = time.time() - self.reporter.timeline.t0
            await asyncio.sleep(max(0.0, target.recorder.lead_in - elapsed))
        self.log("info", "--- steps")
        await self.engine.run_section("steps", parsed.sections["steps"])
        if self.recording:
            await asyncio.sleep(target.recorder.tail)

    async def _collect_evidence(self, abort: StepAbort) -> None:
        """Spec 12: screenshot, every console's text, the step, its expected condition and
        the last 50 lines of output."""
        step, error = abort.step, abort.error
        mask = self.reporter.mask
        details = {k: mask(str(v)) for k, v in error.details.items() if v is not None}
        self.failure = {
            "step": step.path_str(),
            "line": step.loc.line if step.loc else None,
            "summary": mask(step.summary()),
            "error": mask(str(error)),
            **details,
        }
        if self.recording and self.display:
            path = self.dir / "screenshots" / "failure.png"
            if await take_screenshot(self.display, path):
                self.failure["screenshot"] = "screenshots/failure.png"
        if self.session is None:
            return
        failing = details.get("console") or step.console or (self.ctx.current if self.ctx else None)
        for name, console in self.session.consoles.items():
            try:
                lines = await console.history()
            except EnvironmentProblem:
                continue
            tail = [ln for ln in lines][-50:]
            while tail and not tail[-1].strip():
                tail.pop()
            if name == failing:
                self.failure["last_output"] = tail
            self.log("error", f"console {name!r}, last {len(tail)} lines:\n" + "\n".join(
                f"    | {ln}" for ln in tail))
        if "expected" in details:
            self.log("error", f"expected: {details['expected']}")

    async def _wrap_up(self) -> None:
        if self.recording:
            await self.recorder.stop()
        if self.session is not None and self.engine is not None:
            await self._run_finally()
            await self._write_transcripts()
        keep_video = self.status == "success" or self.parsed.model.defaults.keep_video_on_fail
        video = await self.recorder.finalize(keep_video)
        if self.recorder.frame0_wall():
            self.reporter.timeline.t0 = self.recorder.frame0_wall()
        self._write_resolved()
        self.reporter.write_outputs(self._summary(video.name if video else None))
        if self.status == "success":
            self.log("info", f"take finished: {self.dir}")
        else:
            self.log("error", f"take {self.status} (exit code {int(self.exit)}): {self.dir}")
        await self._cleanup()

    async def _run_finally(self) -> None:
        steps = self.parsed.sections.get("finally", [])
        if not steps or self.engine is None:
            return
        self.log("info", "--- finally (not recorded)")
        try:
            await self.engine.run_section("finally", steps)
        except StepAbort as e:
            self.log("error", f"a `finally` step failed: {e}")
            if self.status == "success":
                self.status, self.exit = "failed", ExitCode.STEP_FAILED
                self.failure = {"step": e.step.path_str(), "error": str(e)}
        except EnvironmentProblem as e:
            self.log("error", f"`finally` could not run: {e}")
        except ControlSignal as e:
            self.log("warning", f"`finally` ended early: {e}")

    async def _write_transcripts(self) -> None:
        assert self.session
        for name, console in self.session.consoles.items():
            try:
                lines = await console.history()
            except EnvironmentProblem:
                continue
            while lines and not lines[-1].strip():
                lines.pop()
            self.reporter.write_text(f"transcript/{name}.txt", "\n".join(lines) + "\n")

    def _write_resolved(self) -> None:
        """Spec 10.2: the scenario with includes inlined and `vars` holding the values the
        take started with (file vars, --var, --vars). {{ }} inside steps is filled in as
        each step runs, so the templates themselves stay."""
        yaml = YAML()
        yaml.default_flow_style = False
        data = resolve_includes(self.parsed.raw, self.parsed.file)
        if self.initial_vars is not None:
            data["vars"] = self.initial_vars
        buf = io.StringIO()
        buf.write(f"# Resolved scenario for take {self.id} (from {self.parsed.file}).\n")
        yaml.dump(data, buf)
        self.reporter.write_text("scenario.resolved.yaml", buf.getvalue())

    def _summary(self, video: str | None) -> dict[str, Any]:
        finished = time.time()
        ctx = self.ctx
        return {
            "status": self.status,
            "exit_code": int(self.exit),
            "take_id": self.id,
            "scenario": str(self.parsed.file),
            "title": self.parsed.title,
            "started_at": self.info.started_at,
            "finished_at": datetime.fromtimestamp(finished).isoformat(timespec="seconds"),
            "duration": round(finished - self.reporter.started, 3),
            "recorded": self.recording,
            "video": video,
            "failure": self.failure,
            "executed_mismatches": ctx.executed_mismatches if ctx else [],
        }

    async def _cleanup(self) -> None:
        if self.session is not None:
            if self.opts.keep_session:
                self.log("info", f"session kept: tmux -L {self.session.tmux.socket} attach")
            else:
                await self.session.close()
                await self.session.transport.remove_tree(self.runtime_dir)
        if self.terminal is not None and not self.opts.keep_session:
            await self.terminal.close()


async def run_take(parsed: ParsedScenario, opts: RunOptions) -> int:
    return await Take(parsed, opts).run()
