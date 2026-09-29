"""How the runner reaches the Linux machine: local processes now, SSH in phase 4."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Result:
    rc: int
    out: str
    err: str


class Process(ABC):
    """A long-running process on the target (the screen recorder)."""

    returncode: int | None

    @abstractmethod
    async def write(self, data: bytes) -> None: ...

    @abstractmethod
    async def close_stdin(self) -> None: ...

    @abstractmethod
    async def readline(self) -> bytes:
        """A line of stdout; b"" at end of file."""

    @abstractmethod
    async def wait(self) -> int: ...

    @abstractmethod
    def kill(self) -> None: ...

    @abstractmethod
    def interrupt(self) -> None:
        """Send SIGINT (how wf-recorder is told to finish its file)."""


class Transport(ABC):
    #: True when the target is this machine (files need no copying).
    is_local: bool = True

    @abstractmethod
    async def start(self, argv: list[str], *, stderr_path: str | None = None,
                    env: dict[str, str] | None = None) -> Process:
        """Start a process with piped stdin/stdout; stderr goes to a file on the target."""

    @abstractmethod
    async def fetch(self, remote: str, local: str) -> None:
        """Copy a file from the target to this machine."""

    @abstractmethod
    async def exists(self, path: str) -> bool: ...

    @abstractmethod
    async def remove_file(self, path: str) -> None:
        """Delete a file on the target, ignoring a missing one."""

    async def close(self) -> None:  # noqa: B027  (optional hook; local transports have none)
        """Release connections."""

    @abstractmethod
    async def run(self, argv: list[str], *, input: str | None = None,
                  timeout: float | None = 30.0, env: dict[str, str] | None = None) -> Result:
        """Run a command to completion on the target."""

    @abstractmethod
    async def read_file(self, path: str) -> str | None:
        """Read a text file on the target; None if it does not exist."""

    @abstractmethod
    async def write_file(self, path: str, content: str, mode: int = 0o600) -> None:
        """Create or replace a text file on the target."""

    @abstractmethod
    async def make_dir(self, path: str, mode: int = 0o700) -> None:
        """Create a directory (and parents) on the target."""

    @abstractmethod
    async def remove_tree(self, path: str) -> None:
        """Delete a directory tree on the target, ignoring errors."""

    @abstractmethod
    def expand_user(self, path: str) -> str:
        """Expand ~ the way the target's shell would."""
