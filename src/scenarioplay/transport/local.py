from __future__ import annotations

import asyncio
import os
import shutil
import signal
from pathlib import Path

from .base import Process, Result, Transport


class LocalProcess(Process):
    def __init__(self, proc: asyncio.subprocess.Process):
        self.proc = proc

    @property
    def returncode(self) -> int | None:  # type: ignore[override]
        return self.proc.returncode

    async def write(self, data: bytes) -> None:
        assert self.proc.stdin
        self.proc.stdin.write(data)
        await self.proc.stdin.drain()

    async def close_stdin(self) -> None:
        if self.proc.stdin:
            self.proc.stdin.close()

    async def readline(self) -> bytes:
        assert self.proc.stdout
        return await self.proc.stdout.readline()

    async def wait(self) -> int:
        return await self.proc.wait()

    def kill(self) -> None:
        if self.proc.returncode is None:
            self.proc.kill()

    def interrupt(self) -> None:
        if self.proc.returncode is None:
            self.proc.send_signal(signal.SIGINT)


def clean_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Environment for child processes: no inherited tmux client, a UTF-8 locale."""
    env = {k: v for k, v in os.environ.items() if k not in ("TMUX", "TMUX_PANE")}
    locale = env.get("LC_ALL") or env.get("LC_CTYPE") or env.get("LANG") or ""
    if "UTF-8" not in locale.upper() and "UTF8" not in locale.upper():
        env.pop("LC_ALL", None)
        env["LANG"] = "C.UTF-8"
    if extra:
        env.update(extra)
    return env


class LocalTransport(Transport):
    is_local = True

    def __init__(self) -> None:
        self.env = clean_env()

    async def run(self, argv: list[str], *, input: str | None = None,
                  timeout: float | None = 30.0, env: dict[str, str] | None = None) -> Result:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE if input is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**self.env, **(env or {})},
        )
        try:
            out, err = await asyncio.wait_for(
                proc.communicate(input.encode() if input is not None else None), timeout)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            if proc.returncode is None:
                proc.kill()
                await proc.wait()
            raise
        return Result(proc.returncode or 0, out.decode("utf-8", "replace"),
                      err.decode("utf-8", "replace"))

    async def read_file(self, path: str) -> str | None:
        try:
            return Path(path).read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            return None

    async def write_file(self, path: str, content: str, mode: int = 0o600) -> None:
        p = Path(path)
        p.write_text(content, encoding="utf-8")
        os.chmod(p, mode)

    async def make_dir(self, path: str, mode: int = 0o700) -> None:
        Path(path).mkdir(parents=True, exist_ok=True, mode=mode)

    async def remove_tree(self, path: str) -> None:
        shutil.rmtree(path, ignore_errors=True)

    def expand_user(self, path: str) -> str:
        return os.path.expanduser(path)

    async def start(self, argv: list[str], *, stderr_path: str | None = None,
                    env: dict[str, str] | None = None) -> Process:
        stderr = open(stderr_path, "ab") if stderr_path else asyncio.subprocess.DEVNULL
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=stderr, env={**self.env, **(env or {})})
        finally:
            if stderr_path:
                stderr.close()  # type: ignore[union-attr]
        return LocalProcess(proc)

    async def fetch(self, remote: str, local: str) -> None:
        if os.path.abspath(remote) != os.path.abspath(local):
            shutil.copyfile(remote, local)

    async def exists(self, path: str) -> bool:
        return os.path.exists(path)

    async def remove_file(self, path: str) -> None:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
