"""How the runner reaches the Linux machine: local processes now, SSH in phase 4."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Result:
    rc: int
    out: str
    err: str


class Transport(ABC):
    @abstractmethod
    async def run(self, argv: list[str], *, input: str | None = None,
                  timeout: float | None = 30.0) -> Result:
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
