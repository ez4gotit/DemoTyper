"""The target reached over SSH (spec 4.1, vmware target): asyncssh, one connection.

Each tmux call is one exec channel on the same connection, so a keystroke costs one round
trip. Works from a Windows or Linux host; logins are key-based (spec 13, security).
"""

from __future__ import annotations

import asyncio
import os
import shlex

import asyncssh

from ..errors import EnvironmentProblem
from .base import Process, Result, Transport


def _command(argv: list[str], env: dict[str, str] | None, cwd: str | None = None) -> str:
    cmd = shlex.join(argv)
    if env:
        cmd = "env " + " ".join(shlex.quote(f"{k}={v}") for k, v in env.items()) + " " + cmd
    if cwd:
        cmd = f"cd {shlex.quote(cwd)} && {cmd}"
    return cmd


class SSHProcess(Process):
    def __init__(self, proc: asyncssh.SSHClientProcess):
        self.proc = proc

    @property
    def returncode(self) -> int | None:  # type: ignore[override]
        return self.proc.returncode if self.proc.exit_status is not None else None

    async def write(self, data: bytes) -> None:
        self.proc.stdin.write(data)
        await self.proc.stdin.drain()

    async def close_stdin(self) -> None:
        self.proc.stdin.write_eof()

    async def readline(self) -> bytes:
        return await self.proc.stdout.readline()

    async def wait(self) -> int:
        completed = await self.proc.wait(check=False)
        return completed.exit_status if completed.exit_status is not None else -1

    def kill(self) -> None:
        try:
            self.proc.kill()
        except (OSError, asyncssh.Error):
            self.proc.close()

    def interrupt(self) -> None:
        try:
            self.proc.send_signal("INT")
        except (OSError, asyncssh.Error):
            self.proc.close()


class SSHTransport(Transport):
    is_local = False

    def __init__(self, host: str, *, port: int = 22, user: str | None = None,
                 key: str | None = None, known_hosts: str | None = "~/.ssh/known_hosts",
                 connect_timeout: float = 10.0):
        self.host, self.port, self.user = host, port, user
        self.key = os.path.expanduser(key) if key else None
        self.known_hosts = os.path.expanduser(known_hosts) if known_hosts else None
        self.connect_timeout = connect_timeout
        self.conn: asyncssh.SSHClientConnection | None = None
        self.home = "~"

    @property
    def where(self) -> str:
        return f"{self.user + '@' if self.user else ''}{self.host}:{self.port}"

    async def connect(self) -> None:
        options = dict(port=self.port, username=self.user, connect_timeout=self.connect_timeout)
        if self.key:
            options["client_keys"] = [self.key]
        if self.known_hosts is None or not os.path.exists(self.known_hosts):
            options["known_hosts"] = None  # no known_hosts file: accept (like accept-new)
        else:
            options["known_hosts"] = self.known_hosts
        try:
            self.conn = await asyncssh.connect(self.host, **options)
        except (OSError, asyncssh.Error, asyncio.TimeoutError) as e:
            raise EnvironmentProblem(f"cannot connect over SSH to {self.where}: {e}") from None
        res = await self.run(["sh", "-c", 'printf %s "$HOME"'])
        self.home = res.out.strip() or "~"

    async def wait_connect(self, deadline_s: float) -> None:
        """Keep trying until the guest's sshd answers (it may still be booting)."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + deadline_s
        while True:
            try:
                await self.connect()
                return
            except EnvironmentProblem:
                if loop.time() >= deadline:
                    raise
                await asyncio.sleep(2)

    async def close(self) -> None:
        if self.conn is not None:
            self.conn.close()
            try:
                await self.conn.wait_closed()
            except (OSError, asyncssh.Error):
                pass
            self.conn = None

    def _require(self) -> asyncssh.SSHClientConnection:
        if self.conn is None:
            raise EnvironmentProblem(f"not connected to {self.where}")
        return self.conn

    async def run(self, argv: list[str], *, input: str | None = None,
                  timeout: float | None = 30.0, env: dict[str, str] | None = None) -> Result:
        conn = self._require()
        try:
            res = await asyncio.wait_for(
                conn.run(_command(argv, env), input=input, check=False), timeout)
        except (asyncssh.ConnectionLost, asyncssh.DisconnectError, OSError) as e:
            raise EnvironmentProblem(f"SSH connection to {self.where} lost: {e}") from None
        out = res.stdout if isinstance(res.stdout, str) else (res.stdout or b"").decode()
        err = res.stderr if isinstance(res.stderr, str) else (res.stderr or b"").decode()
        return Result(res.exit_status if res.exit_status is not None else -1, out or "",
                      err or "")

    async def start(self, argv: list[str], *, stderr_path: str | None = None,
                    env: dict[str, str] | None = None) -> Process:
        conn = self._require()
        cmd = _command(argv, env)
        if stderr_path:
            cmd += f" 2>>{shlex.quote(stderr_path)}"
        proc = await conn.create_process(cmd, encoding=None)
        return SSHProcess(proc)

    async def read_file(self, path: str) -> str | None:
        res = await self.run(["cat", path])
        return res.out if res.rc == 0 else None

    async def write_file(self, path: str, content: str, mode: int = 0o600) -> None:
        res = await self.run(["sh", "-c", f"umask 077; cat > {shlex.quote(path)} && "
                                          f"chmod {mode:o} {shlex.quote(path)}"],
                             input=content)
        if res.rc != 0:
            raise EnvironmentProblem(f"cannot write {path} on {self.where}: {res.err.strip()}")

    async def make_dir(self, path: str, mode: int = 0o700) -> None:
        await self.run(["mkdir", "-p", "-m", f"{mode:o}", path])

    async def remove_tree(self, path: str) -> None:
        await self.run(["rm", "-rf", path])

    async def remove_file(self, path: str) -> None:
        await self.run(["rm", "-f", path])

    async def exists(self, path: str) -> bool:
        return (await self.run(["test", "-e", path])).rc == 0

    async def fetch(self, remote: str, local: str) -> None:
        conn = self._require()
        async with conn.start_sftp_client() as sftp:
            await sftp.get(remote, local)

    def expand_user(self, path: str) -> str:
        if path == "~":
            return self.home
        if path.startswith("~/"):
            return self.home + path[1:]
        return path
