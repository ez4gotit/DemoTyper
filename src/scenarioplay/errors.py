from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class Location:
    file: str
    line: int
    col: int

    def __str__(self) -> str:
        return f"{self.file}:{self.line}:{self.col}"


@dataclass
class Problem:
    message: str
    loc: Location | None = None
    severity: Literal["error", "warning"] = "error"

    def format(self) -> str:
        prefix = f"{self.loc}: " if self.loc else ""
        return f"{prefix}{self.severity}: {self.message}"


class ScenarioInvalid(Exception):
    """The scenario file cannot be loaded; carries every problem found."""

    def __init__(self, problems: list[Problem]):
        super().__init__("\n".join(p.format() for p in problems))
        self.problems = problems


class EnvironmentProblem(Exception):
    """The machine is not ready to run a take (exit code 3)."""


class TmuxError(EnvironmentProblem):
    pass


class StepFailed(Exception):
    """A step could not do its job. `details` goes into the evidence."""

    def __init__(self, message: str, **details: Any):
        super().__init__(message)
        self.details = details


class WaitTimeout(StepFailed):
    pass


class ConsoleLost(StepFailed):
    pass


class ControlSignal(Exception):
    """break / continue / stop: unwinds the step tree without being a failure."""


class BreakLoop(ControlSignal):
    pass


class ContinueLoop(ControlSignal):
    pass


class StopTake(ControlSignal):
    def __init__(self, status: str, message: str | None):
        super().__init__(message or f"stopped ({status})")
        self.status = status
        self.message = message


@dataclass
class StepAbort(Exception):
    """An unhandled step failure that ends the take."""

    step: Any
    error: StepFailed
    extra: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return str(self.error)
