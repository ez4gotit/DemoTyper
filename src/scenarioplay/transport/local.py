from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path

from .base import Result, Transport


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
    def __init__(self) -> None:
        self.env = clean_env()

    async def run(self, argv: list[str], *, input: str | None = None,
                  timeout: float | None = 30.0) -> Result:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE if input is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self.env,
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
