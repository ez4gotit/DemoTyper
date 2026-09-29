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
import shutil
import signal
import sys
import tempfile
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from ..console import Session
from ..console.cast import CastRecorder
from ..console.session import SESSION
from ..console.terminal import TerminalWindow
from ..errors import ControlSignal, EnvironmentProblem, StepAbort, StopTake
from ..exitcodes import ExitCode
from ..loader import ParsedScenario
from ..loader.load import resolve_includes
from ..recorder import NullRecorder, Recorder, X11Recorder
from ..recorder.host import HostRecorder, default_source
from ..recorder.wayland import WfRecorder
from ..report import Reporter
from ..secretstore import load_secrets, referenced_secrets
from ..target.vmrun import display_name
from ..target.vmware import VMwareTarget
from ..transport import LocalTransport, Transport
from .context import RunContext, RunOptions, TakeInfo
from .engine import Engine
from .selection import select


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
        self.kind = opts.target_kind or target.kind
        if self.kind == "vmware":
            # The guest's display; the runner reaches it over SSH.
            self.display = opts.display if target.record == "guest" and opts.display \
                else (target.recorder.display or ":0")
            self.headless = opts.headless
            self.runtime_dir = f"/tmp/scenarioplay-{self.id}"
        else:
            self.display = opts.display or target.recorder.display or os.environ.get("DISPLAY")
            self.headless = opts.headless or (not opts.record and not self.display)
            self.runtime_dir = os.path.join(
                os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir(),
                f"scenarioplay-{self.id}")
        self.recorder: Recorder = NullRecorder()
        self.recording = False
        self.session: Session | None = None
        self.terminal: TerminalWindow | None = None
        self.ctx: RunContext | None = None
        self.engine: Engine | None = None
        self.vm: VMwareTarget | None = None
        self.earlier_text: dict[str, list[str]] = {}  # console text from before a vm reboot
        self.transport: Transport | None = None
        self.x_env: dict[str, str] = {}
        self.status = "success"
        self.exit = ExitCode.OK
        self.failure: dict[str, Any] | None = None
        self.initial_vars: dict[str, Any] | None = None
        self.casts: CastRecorder | None = None
        self._interrupted = False
        self._task: asyncio.Task[Any] | None = None

    def log(self, level: str, message: str) -> None:
        self.reporter.log(level, message)

    # --- the take ------------------------------------------------------------------------

    async def run(self) -> int:
        self._task = asyncio.current_task()
        loop = asyncio.get_running_loop()
        previous = None
        try:
            loop.add_signal_handler(signal.SIGINT, self._on_sigint)
        except (NotImplementedError, RuntimeError):
            # Windows (runner on a VMware host): no loop signal handlers; hand Ctrl+C over.
            previous = signal.signal(
                signal.SIGINT, lambda *_: loop.call_soon_threadsafe(self._on_sigint))
        self.log("info", f"take {self.id}: {self.parsed.file} -> {self.dir}")
        try:
            await self._play()
        except StopTake as e:
            if e.status == "success":
                self.log("info", f"stopped early: {e}")
            elif e.status == "interrupted":
                self.status, self.exit = "interrupted", ExitCode.INTERRUPTED
                self.failure = {"error": str(e)}
                self.log("warning", f"stopped: {e}")
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
                if previous is not None:
                    signal.signal(signal.SIGINT, previous)
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
        if self.kind == "local":
            if sys.platform != "linux":
                raise EnvironmentProblem(
                    "the local target runs on the Linux machine itself; run scenarioplay "
                    "there (for example in WSL), or use the vmware target from this host")
            if opts.record and not self.display and self._backend() == "x11grab":
                raise EnvironmentProblem("no X display to record ($DISPLAY is not set); pass "
                                         "--display, or rehearse with --no-record")
        elif not target.vmx:
            raise EnvironmentProblem("--target vmware needs target.vmx in the scenario")
        # Resolve secrets before touching anything, so a missing one costs nothing.
        secret_values = load_secrets(referenced_secrets(parsed), opts.secrets_file, self.log)
        for value in secret_values.values():
            self.reporter.mask.register(value)
        if secret_values:
            self.log("info", f"secrets loaded: {', '.join(sorted(secret_values))}")

        if self.kind == "vmware":
            self.vm = VMwareTarget(target, self.log)
            transport: Transport = await self.vm.prepare()
            self.x_env = self.vm.x_env
        else:
            transport = LocalTransport()
        self.transport = transport
        await self._open_consoles(transport, list(c.name for c in parsed.model.consoles
                                                  if c.start))

        self.ctx = RunContext(parsed, opts, self.info, self.reporter, self.session,
                              self.recorder, None if self.headless else self.display)
        self.ctx.secrets = secret_values
        self.ctx.make_scope(parsed.model.vars, opts.cli_vars, opts.vars_file)
        self.ctx.restart_guest = self.restart_guest
        self.ctx.vm = self.vm
        self.initial_vars = self.ctx.scope.snapshot()
        self.engine = Engine(self.ctx)

        setup = parsed.sections.get("setup", [])
        if setup:
            self.log("info", "--- setup (not recorded)")
            await self.engine.run_section("setup", setup)
            if parsed.model.defaults.clear_after_setup:
                await self.session.clear()

        if opts.record:
            recorder = self._make_recorder()
            recorder.on_death = self._task.cancel if self._task else None
            self.recorder = recorder
            self.ctx.recorder = recorder
            await recorder.start()
            self.recording = True
            self.reporter.timeline.segments = recorder.segments  # updated in place
        self.reporter.timeline.t0 = self.recorder.frame0_wall() or time.time()
        if opts.cast:
            self.casts = CastRecorder(self.runtime_dir)
            for console in self.session.consoles.values():
                await self.casts.start(console, self.reporter.timeline.t0 or time.time(),
                                       parsed.title)
        if self.recording:
            # The lead-in counts from the first frame, which ffmpeg captured a moment
            # before it reported it.
            elapsed = time.time() - self.reporter.timeline.t0
            await asyncio.sleep(max(0.0, target.recorder.lead_in - elapsed))
        steps = parsed.sections["steps"]
        first, stop = select(steps, opts.from_name, opts.to_name)
        if (first, stop) != (0, len(steps)):
            self.log("info", f"running steps {first + 1}-{stop} of {len(steps)} "
                             f"(--from/--to); `setup` and `finally` run as usual")
        self.log("info", "--- steps")
        await self.engine.run_section("steps", steps[first:stop])
        if self.recording:
            await asyncio.sleep(target.recorder.tail)

    async def _open_consoles(self, transport: Transport, names: list[str]) -> None:
        """tmux session, terminal window, first prompts. Also used after a guest revert."""
        target = self.parsed.model.target
        self.session = Session(transport, self.runtime_dir, self.id, self.log)
        model = self.parsed.model
        if set(names) != {c.name for c in model.consoles if c.start}:
            # After a revert: reopen the consoles that were open, not the declared set.
            starts = {c.name: c.name in names for c in model.consoles}
            consoles = [c.model_copy(update={"start": starts[c.name]}) for c in model.consoles]
            first = next(c for c in consoles if c.start)
            consoles.remove(first)
            consoles.insert(0, first)
            model = model.model_copy(update={"consoles": consoles})
        await self.session.create(model, self.opts.width, self.opts.height)
        if not self.headless:
            assert self.display
            attach = self.session.tmux.argv("attach-session", "-t", SESSION)
            self.terminal = TerminalWindow(target.terminal, attach, self.display, transport,
                                           self.x_env)
            await self.terminal.open()
            await self.session.wait_attached()
            await self.session.arrange()  # pane sizes for the terminal's real size
        else:
            self.log("info", "headless: no terminal window (attach with: "
                             f"tmux -L {self.session.tmux.socket} attach)")
        await self.session.wait_ready()

    def _make_recorder(self) -> Recorder:
        target = self.parsed.model.target
        if self.kind == "vmware" and target.record == "host":
            assert self.vm is not None and target.vmx
            source = self.opts.display or default_source(display_name(target.vmx))
            self.log("info", f"recording on the host (mode B): {source}")
            return HostRecorder(target.recorder, source, self.dir, self.log)
        cls = WfRecorder if self._backend() == "wf-recorder" else X11Recorder
        return cls(target.recorder, self.display or "", self.dir, self.log,
                   transport=self.transport, workdir=self.runtime_dir, env=self.x_env)

    def _backend(self) -> str:
        backend = self.parsed.model.target.recorder.backend
        if backend != "auto":
            return backend
        # A local Wayland session with wf-recorder installed; otherwise X11. (WSLg sets
        # WAYLAND_DISPLAY but has no wf-recorder, and its X display records black.)
        if self.kind == "local" and os.environ.get("WAYLAND_DISPLAY") \
                and shutil.which("wf-recorder"):
            return "wf-recorder"
        return "x11grab"

    async def restart_guest(self, kind: str, snapshot: str | None) -> None:
        """`vm: revert` / `vm: reboot` mid-take (spec 4.4): wait for the guest, then rebuild
        the tmux session, the consoles that were open and the terminal window."""
        assert self.vm is not None and self.session is not None and self.ctx is not None
        open_names = list(self.session.consoles)
        current = self.ctx.current
        # The guest's tmux goes away with the revert/reboot: keep what the consoles showed.
        for name, console in self.session.all_consoles().items():
            try:
                lines = await console.history()
            except EnvironmentProblem:
                continue
            while lines and not lines[-1].strip():
                lines.pop()
            self.earlier_text.setdefault(name, []).extend(
                [*lines, f"--- vm {kind} ---"])
        if self.terminal is not None:
            await self.terminal.close()
        self.transport = await self.vm.restart(kind, snapshot)
        self.x_env = self.vm.x_env
        await self._open_consoles(self.transport, open_names)
        self.ctx.session = self.session
        if current in self.session.consoles:
            self.ctx.current = current
        self.log("info", f"guest back after {kind}; consoles rebuilt: {', '.join(open_names)}")

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
        if self.recording:
            path = self.dir / "screenshots" / "failure.png"
            if await self.recorder.screenshot(path):
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
        if self.casts is not None and self.session is not None:
            for console in self.session.all_consoles().values():
                await self.casts.stop(console)
        if self.session is not None and self.engine is not None:
            await self._run_finally()
            await self._write_transcripts()
            await self._save_casts()
        keep_video = self.status == "success" or self.parsed.model.defaults.keep_video_on_fail
        # finalize() replaces the segments' estimated start times with the exact ones, which
        # the timeline (sharing the list) uses for chapters and subtitles.
        video = await self.recorder.finalize(keep_video)
        self._write_resolved()
        self.reporter.write_outputs(self._summary(video.name if video else None))
        if video is not None and video.suffix == ".mp4" and self.opts.burn_subtitles:
            await self._burn_subtitles(video)
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
        for name, console in self.session.all_consoles().items():
            try:
                lines = await console.history()
            except EnvironmentProblem:
                continue
            while lines and not lines[-1].strip():
                lines.pop()
            lines = [*self.earlier_text.get(name, []), *lines]
            self.reporter.write_text(f"transcript/{name}.txt", "\n".join(lines) + "\n")

    async def _save_casts(self) -> None:
        if self.casts is None or self.session is None:
            return
        transport = self.session.transport
        (self.dir / "cast").mkdir(exist_ok=True)
        for name, remote in self.casts.files.items():
            text = await transport.read_file(remote)
            if text is not None:
                self.reporter.write_text(f"cast/{name}.cast", text)

    async def _burn_subtitles(self, video: Path) -> None:
        """`--burn-subtitles` (spec 10.3): video.mp4 gets the subtitles drawn in; the
        original is kept as video.clean.mp4."""
        if not (self.dir / "subtitles.srt").exists():
            self.log("info", "no subtitles to burn in")
            return
        clean = self.dir / "video.clean.mp4"
        video.rename(clean)
        spec = self.parsed.model.target.recorder
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", clean.name,
            "-vf", "subtitles=subtitles.srt:force_style='FontSize=22,MarginV=28'",
            "-c:v", spec.codec, "-preset", spec.preset, "-crf", str(spec.crf),
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", video.name,
            cwd=self.dir, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
        _, err = await proc.communicate()
        if proc.returncode == 0:
            self.log("info", "subtitles burned into video.mp4 (original: video.clean.mp4)")
        else:
            clean.rename(video)
            self.log("warning", "could not burn in the subtitles (ffmpeg needs libass): "
                                f"{err.decode(errors='replace').strip()[-300:]}")

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
        if self.transport is not None and not self.transport.is_local:
            await self.transport.close()


async def run_take(parsed: ParsedScenario, opts: RunOptions) -> int:
    return await Take(parsed, opts).run()
