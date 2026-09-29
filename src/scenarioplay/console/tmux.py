"""Thin async wrapper over the tmux command line, on a private server socket."""

from __future__ import annotations

import re

from ..errors import EnvironmentProblem, TmuxError
from ..transport import Transport

MIN_VERSION = (3, 0)

_NAMED = {
    "enter": "Enter", "return": "Enter", "tab": "Tab", "btab": "BTab", "escape": "Escape",
    "esc": "Escape", "space": "Space", "bspace": "BSpace", "backspace": "BSpace",
    "delete": "DC", "del": "DC", "dc": "DC", "insert": "IC", "ic": "IC", "home": "Home",
    "end": "End", "pageup": "PPage", "pgup": "PPage", "ppage": "PPage", "pagedown": "NPage",
    "pgdn": "NPage", "npage": "NPage", "up": "Up", "down": "Down", "left": "Left",
    "right": "Right",
}
_NAMED.update({f"f{i}": f"F{i}" for i in range(1, 13)})
_KEY_RE = re.compile(r"^((?:[CMS]-)*)(.+)$")


def tmux_key(name: str) -> str | None:
    """Translate a scenario key name (C-c, Tab, PageUp, M-x, F5...) to tmux's name, or None."""
    m = _KEY_RE.match(name)
    if not m:
        return None
    mods, base = m.group(1), m.group(2)
    if len(base) == 1 and base.isprintable():
        return mods + base
    named = _NAMED.get(base.lower())
    return mods + named if named else None


def parse_version(text: str) -> tuple[int, int]:
    m = re.search(r"(\d+)\.(\d+)", text)
    if not m:
        raise EnvironmentProblem(f"cannot parse tmux version from {text.strip()!r}")
    return int(m.group(1)), int(m.group(2))


class Tmux:
    def __init__(self, transport: Transport, socket: str):
        self.transport = transport
        self.socket = socket
        self.version: tuple[int, int] = MIN_VERSION

    async def detect_version(self) -> tuple[int, int]:
        try:
            res = await self.transport.run(["tmux", "-V"])
        except FileNotFoundError:
            raise EnvironmentProblem("tmux is not installed on the target") from None
        if res.rc != 0:
            raise EnvironmentProblem(f"`tmux -V` failed: {res.err.strip()}")
        self.version = parse_version(res.out)
        if self.version < MIN_VERSION:
            raise EnvironmentProblem(
                f"tmux {self.version[0]}.{self.version[1]} is too old; 3.0 or newer is needed")
        return self.version

    def argv(self, *args: str) -> list[str]:
        return ["tmux", "-L", self.socket, *args]

    async def __call__(self, *args: str, check: bool = True, timeout: float = 10.0) -> str:
        res = await self.transport.run(self.argv(*args), timeout=timeout)
        if check and res.rc != 0:
            raise TmuxError(f"tmux {args[0]} failed: {res.err.strip() or res.out.strip()}")
        return res.out

    async def send_literal(self, target: str, text: str) -> None:
        # tmux treats an argument ending in ";" as a command separator; "\;" is a literal ";".
        if text.endswith(";"):
            text = text[:-1] + "\\;"
        await self("send-keys", "-t", target, "-l", "--", text)

    async def send_key(self, target: str, key: str) -> None:
        await self("send-keys", "-t", target, key)

    async def kill_server(self) -> None:
        await self("kill-server", check=False)
