"""Console objects: one tmux pane each. Types, sends keys, reads the screen."""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass

from ..loader.model import ConsoleSpec
from ..transport import Result
from .remote import remote_run_argv
from .tmux import Tmux

_INFO_FORMAT = ("#{history_size} #{cursor_x} #{cursor_y} #{alternate_on} #{pane_dead} "
                "#{pane_width} #{pane_height}")


@dataclass(frozen=True)
class PaneInfo:
    history_size: int
    cursor_x: int
    cursor_y: int
    alternate_on: bool
    dead: bool
    width: int
    height: int

    @property
    def cursor_abs(self) -> int:
        """The cursor's line counted from the oldest line in the scrollback."""
        return self.history_size + self.cursor_y


@dataclass(frozen=True)
class ShellStatus:
    """What the hidden shell hook wrote at the last prompt."""

    seq: int
    exit_code: int
    command: str


def parse_status(text: str | None) -> ShellStatus | None:
    if not text:
        return None
    first, _, rest = text.partition("\n")
    parts = first.split()
    if len(parts) != 2 or not all(p.lstrip("-").isdigit() for p in parts):
        return None
    return ShellStatus(int(parts[0]), int(parts[1]), rest.strip())


class Console:
    def __init__(self, spec: ConsoleSpec, tmux: Tmux, pane: str, prompt: str,
                 status_path: str | None):
        self.spec = spec
        self.name = spec.name
        self.tmux = tmux
        self.pane = pane
        self.prompt_re = re.compile(prompt)
        self.status_path = status_path
        # True once the hook has reported at least one prompt.
        self.hook_ok = False
        # Absolute line where output of the last input starts (for scope since_last_input).
        self.output_start: int | None = None
        # Hook sequence number when input was last sent; the prompt counts as back only
        # after the sequence moves past it.
        self.enter_seq: int | None = None
        # (absolute line, column) where the text of the current command line starts.
        self.input_start: tuple[int, int] | None = None
        self._tty: str | None = None
        self.window: str | None = None  # tmux window id
        self.closed = False
        self.final_history: list[str] | None = None  # kept when the console is closed

    @property
    def remote(self) -> bool:
        return self.spec.host is not None

    async def run_out_of_view(self, command: str, *, cwd: str | None = None,
                              timeout: float = 30.0) -> Result:
        """Run a shell command on this console's machine without typing it on screen."""
        transport = self.tmux.transport
        if self.remote:
            return await transport.run(remote_run_argv(self.spec, command, cwd),
                                       timeout=timeout)
        where = transport.expand_user(cwd or self.spec.cwd)
        return await transport.run(
            ["bash", "-c", f"cd {shlex.quote(where)} 2>/dev/null; {command}"], timeout=timeout)

    # --- reading -----------------------------------------------------------------------

    async def info(self) -> PaneInfo:
        out = await self.tmux("display-message", "-p", "-t", self.pane, _INFO_FORMAT)
        f = out.split()
        return PaneInfo(int(f[0]), int(f[1]), int(f[2]), f[3] == "1", f[4] == "1",
                        int(f[5]), int(f[6]))

    async def capture(self, start_abs: int | None = None, end_abs: int | None = None, *,
                      join: bool = True, info: PaneInfo | None = None) -> list[str]:
        """Lines of the pane. Without start_abs: the visible screen. Lines are absolute
        indexes into scrollback + screen (see PaneInfo.cursor_abs)."""
        args = ["capture-pane", "-p", "-t", self.pane]
        if join:
            args.append("-J")
        elif self.tmux.version >= (3, 1):
            args.append("-N")
        if start_abs is not None or end_abs is not None:
            info = info or await self.info()
            if start_abs is not None:
                rel = max(start_abs - info.history_size, -info.history_size)
                if rel > info.height - 1:
                    return []
                args += ["-S", str(rel)]
            if end_abs is not None:
                args += ["-E", str(end_abs - info.history_size)]
            else:
                args += ["-E", "-"]
        out = await self.tmux(*args)
        lines = out.split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        return lines

    async def command_output(self) -> str:
        """Output of the last command: from after its Enter up to the returned prompt."""
        if self.output_start is None:
            return ""
        lines = await self.capture(start_abs=self.output_start)
        while lines and not lines[-1].strip():
            lines.pop()
        if lines and self.prompt_matches(lines[-1]):
            lines.pop()
        return "\n".join(line.rstrip() for line in lines)

    async def history(self) -> list[str]:
        """Everything in the pane, scrollback included (for transcripts)."""
        if self.final_history is not None:
            return self.final_history
        out = await self.tmux("capture-pane", "-p", "-J", "-t", self.pane, "-S", "-", "-E", "-")
        return out.rstrip("\n").split("\n")

    async def status(self) -> ShellStatus | None:
        if not self.status_path:
            return None
        return parse_status(await self.tmux.transport.read_file(self.status_path))

    def prompt_matches(self, line: str) -> bool:
        return bool(self.prompt_re.search(line) or self.prompt_re.search(line.rstrip()))

    async def current_line_before_cursor(self, info: PaneInfo | None = None) -> str:
        info = info or await self.info()
        lines = await self.capture(info.cursor_abs, info.cursor_abs, join=False, info=info)
        line = lines[0] if lines else ""
        return line.ljust(info.cursor_x)[: info.cursor_x]

    async def read_input(self) -> str | None:
        """Text typed on the current command line: from input_start to the cursor."""
        if self.input_start is None:
            return None
        info = await self.info()
        y0, x0 = self.input_start
        y1, x1 = info.cursor_abs, info.cursor_x
        if y1 < y0:
            return None
        lines = await self.capture(y0, y1, join=False, info=info)
        if len(lines) != y1 - y0 + 1:
            return None
        lines = [ln.ljust(info.width) for ln in lines]
        if len(lines) == 1:
            return lines[0][x0:x1]
        return lines[0][x0:] + "".join(lines[1:-1]) + lines[-1][:x1]

    async def tty_modes(self) -> set[str] | None:
        """Local-mode flags of the pane's terminal, e.g. {"icanon", "-echo", ...}."""
        if self._tty is None:
            self._tty = (await self.tmux("display-message", "-p", "-t", self.pane,
                                         "#{pane_tty}")).strip()
        res = await self.tmux.transport.run(["stty", "-F", self._tty, "-a"])
        if res.rc != 0:
            return None
        return set(re.split(r"[\s;]+", res.out))

    async def input_hidden(self) -> bool | None:
        """True while a program reads a line without echo, as sudo, ssh and passwd do for
        passwords. A shell prompt does not count: its line editor also turns echo off, but
        runs in non-canonical mode. None if the modes cannot be read."""
        modes = await self.tty_modes()
        if modes is None:
            return None
        return "icanon" in modes and "-echo" in modes

    # --- writing -----------------------------------------------------------------------

    async def send_char(self, ch: str) -> None:
        await self.tmux.send_literal(self.pane, ch)

    async def send_key(self, key: str) -> None:
        await self.tmux.send_key(self.pane, key)
