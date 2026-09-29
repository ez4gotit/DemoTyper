"""System conditions checked out of view on the target: exec, file, port (spec 7.1)."""

from __future__ import annotations

import asyncio
import re
import shlex

from pydantic import field_validator

from ..plugins import condition
from .base import Condition, Probe


@condition
class ExecCondition(Condition):
    """An out-of-view command succeeds (exit code 0). Nothing is typed on screen."""

    KEYWORD = "exec"
    exec: str

    def describe(self) -> str:
        return f"`{self.exec}` to succeed"

    async def check(self, probe: Probe) -> str | None:
        try:
            res = await probe.run(self.exec, timeout=max(5.0, (self.interval or 0.2) * 10))
        except asyncio.TimeoutError:
            return None
        return "exit code 0" if res.rc == 0 else None


@condition
class FileCondition(Condition):
    """A file or directory exists on the target (checked out of view)."""

    KEYWORD = "file"
    file: str

    def describe(self) -> str:
        return f"file {self.file} to exist"

    async def check(self, probe: Probe) -> str | None:
        path = self.file
        if path == "~" or path.startswith("~/"):
            # Let the console's machine expand ~ (it may be another machine).
            quoted = "~" + (f"/{shlex.quote(path[2:])}" if len(path) > 2 else "")
        else:
            quoted = shlex.quote(path)
        res = await probe.run(f"test -e {quoted}")
        return path if res.rc == 0 else None


@condition
class PortCondition(Condition):
    """A TCP port accepts connections: `port: 80` (on the target) or `port: "db:5432"`."""

    KEYWORD = "port"
    port: int | str

    @field_validator("port")
    @classmethod
    def _valid(cls, v: int | str) -> int | str:
        if isinstance(v, int):
            if not 0 < v < 65536:
                raise ValueError("a port is a number from 1 to 65535")
            return v
        if "{{" in v:
            return v
        if not re.fullmatch(r"[A-Za-z0-9_.-]+:\d{1,5}|\d{1,5}", v):
            raise ValueError("expected a port number or host:port")
        return v

    def describe(self) -> str:
        return f"port {self.port} to accept connections"

    async def check(self, probe: Probe) -> str | None:
        text = str(self.port)
        host, _, port = text.rpartition(":")
        host = host or "127.0.0.1"
        # bash's /dev/tcp works the same on the local machine and, later, over SSH.
        res = await probe.run(
            f"exec 3<>/dev/tcp/{shlex.quote(host)}/{shlex.quote(port)}", timeout=5.0)
        return f"{host}:{port} open" if res.rc == 0 else None
