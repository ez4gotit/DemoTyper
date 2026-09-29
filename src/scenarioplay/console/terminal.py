"""The visible full-screen terminal window attached to the take's tmux session."""

from __future__ import annotations

import asyncio
import shlex
import shutil
from collections.abc import Callable

from ..errors import EnvironmentProblem
from ..loader.model import TerminalSpec
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


def terminal_argv(spec: TerminalSpec, attach: list[str]) -> list[str]:
    if isinstance(spec.command, list):
        return [*spec.command, *attach]
    if isinstance(spec.command, str):
        if "{attach}" in spec.command:
            return shlex.split(spec.command.replace("{attach}", shlex.join(attach)))
        return [*shlex.split(spec.command), *attach]
    for name, build in TERMINALS:
        if shutil.which(name):
            return build(spec.font, spec.font_size, attach)
    names = ", ".join(n for n, _ in TERMINALS)
    raise EnvironmentProblem(
        f"no terminal emulator found (tried {names}); install one, set target.terminal."
        "command, or use --headless")


def find_terminal() -> str | None:
    return next((name for name, _ in TERMINALS if shutil.which(name)), None)


class TerminalWindow:
    def __init__(self, spec: TerminalSpec, attach: list[str], display: str):
        self.argv = terminal_argv(spec, attach)
        self.display = display
        self.proc: asyncio.subprocess.Process | None = None

    async def open(self) -> None:
        try:
            self.proc = await asyncio.create_subprocess_exec(
                *self.argv, stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
                env=clean_env({"DISPLAY": self.display}), start_new_session=True)
        except FileNotFoundError:
            raise EnvironmentProblem(f"terminal command not found: {self.argv[0]}") from None

    async def close(self) -> None:
        if self.proc and self.proc.returncode is None:
            self.proc.terminate()
            try:
                await asyncio.wait_for(self.proc.wait(), 5)
            except asyncio.TimeoutError:
                self.proc.kill()
