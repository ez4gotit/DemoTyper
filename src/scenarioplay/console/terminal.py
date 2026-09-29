"""The visible full-screen terminal window attached to the take's tmux session. It runs
where the screen is: this machine, or the VMware guest (started over SSH)."""

from __future__ import annotations

import asyncio
import shlex
import shutil
from collections.abc import Callable

from ..errors import EnvironmentProblem
from ..loader.model import TerminalSpec
from ..transport import Transport
from ..transport.base import Process
from ..transport.local import clean_env

Builder = Callable[[str, int, list[str]], list[str]]

# Known terminals, in order of preference: name -> argv builder(font, size, attach argv).
TERMINALS: list[tuple[str, Builder]] = [
    ("xterm", lambda font, size, attach: [
        "xterm", "-fullscreen", "-fa", font, "-fs", str(size), "-bg", "black", "-fg",
        "#d0d0d0", "-u8", "-bc", "+sb", "-xrm", "XTerm*allowWindowOps: false",
        "-e", *attach]),
    ("alacritty", lambda font, size, attach: [
        "alacritty", "-o", f"font.size={size}", "-o", f'font.normal.family="{font}"',
        "-o", 'window.startup_mode="Fullscreen"', "-e", *attach]),
    ("kitty", lambda font, size, attach: [
        "kitty", "--start-as=fullscreen", "-o", f"font_size={size}", "-o",
        f"font_family={font}", *attach]),
    ("gnome-terminal", lambda font, size, attach: [
        "gnome-terminal", "--full-screen", "--wait", "--", *attach]),
    ("xfce4-terminal", lambda font, size, attach: [
        "xfce4-terminal", "--fullscreen", f"--font={font} {size}", "-x", *attach]),
    ("konsole", lambda font, size, attach: ["konsole", "--fullscreen", "-e", *attach]),
]


def find_terminal() -> str | None:
    return next((name for name, _ in TERMINALS if shutil.which(name)), None)


async def terminal_argv(spec: TerminalSpec, attach: list[str],
                        transport: Transport | None = None) -> list[str]:
    if isinstance(spec.command, list):
        return [*spec.command, *attach]
    if isinstance(spec.command, str):
        if "{attach}" in spec.command:
            return shlex.split(spec.command.replace("{attach}", shlex.join(attach)))
        return [*shlex.split(spec.command), *attach]
    for name, build in TERMINALS:
        if transport is None or transport.is_local:
            present = shutil.which(name) is not None
        else:
            present = (await transport.run(["sh", "-c", f"command -v {name}"])).rc == 0
        if present:
            return build(spec.font, spec.font_size, attach)
    names = ", ".join(n for n, _ in TERMINALS)
    where = "" if transport is None or transport.is_local else " in the guest"
    raise EnvironmentProblem(
        f"no terminal emulator found{where} (tried {names}); install one, set "
        "target.terminal.command, or use --headless")


class TerminalWindow:
    def __init__(self, spec: TerminalSpec, attach: list[str], display: str,
                 transport: Transport | None = None, env: dict[str, str] | None = None):
        self.spec = spec
        self.attach = attach
        self.display = display
        self.transport = transport
        self.env = env or {}
        self.proc: asyncio.subprocess.Process | None = None
        self.remote: Process | None = None

    async def open(self) -> None:
        argv = await terminal_argv(self.spec, self.attach, self.transport)
        env = {**self.env, "DISPLAY": self.display}
        if self.transport is not None and not self.transport.is_local:
            self.remote = await self.transport.start(argv, env=env)
            return
        try:
            self.proc = await asyncio.create_subprocess_exec(
                *argv, stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
                env=clean_env(env), start_new_session=True)
        except FileNotFoundError:
            raise EnvironmentProblem(f"terminal command not found: {argv[0]}") from None

    async def close(self) -> None:
        if self.remote is not None:
            self.remote.kill()
            return
        if self.proc and self.proc.returncode is None:
            self.proc.terminate()
            try:
                await asyncio.wait_for(self.proc.wait(), 5)
            except asyncio.TimeoutError:
                self.proc.kill()
