"""Registries for step and condition plugins (spec section 13, extensibility).

Built-in plugins register themselves on import. Third-party packages add classes through the
entry-point groups `scenarioplay.actions` and `scenarioplay.conditions`; each entry point
names a class that subclasses StepModel or Condition.
"""

from __future__ import annotations

from importlib.metadata import entry_points
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from .actions.base import StepModel
    from .conditions.base import Condition

ACTIONS: dict[str, type[StepModel]] = {}
CONDITIONS: dict[str, type[Condition]] = {}

# Scenario-language keywords from the spec that this version does not implement yet,
# mapped to the phase that brings them. Used for friendlier validation errors.
FUTURE_STEPS = {
    "if": 2, "for_each": 2, "repeat": 2, "while": 2, "until": 2, "retry": 2, "try": 2,
    "define": 2, "call": 2, "break": 2, "continue": 2, "stop": 2, "include": 2, "set": 2,
    "capture": 2, "assert": 2, "exec": 2,
    "parallel": 3, "focus": 3, "use": 3, "open_console": 3, "close_console": 3,
    "vm": 4, "record": 4,
}
FUTURE_CONDITIONS = {"gone": 2, "idle": 2, "any": 2, "all": 2, "exec": 2, "file": 2, "port": 2}

S = TypeVar("S", bound="type[StepModel]")
C = TypeVar("C", bound="type[Condition]")


def action(cls: S) -> S:
    """Class decorator that registers a step plugin under its KEYWORD."""
    if not cls.KEYWORD:
        raise ValueError(f"{cls.__name__} has no KEYWORD")
    ACTIONS[cls.KEYWORD] = cls
    return cls


def condition(cls: C) -> C:
    """Class decorator that registers a wait-condition plugin under its KEYWORD."""
    if not cls.KEYWORD:
        raise ValueError(f"{cls.__name__} has no KEYWORD")
    CONDITIONS[cls.KEYWORD] = cls
    return cls


_loaded = False


def load_plugins() -> None:
    """Import the built-in plugins and any installed third-party ones (idempotent)."""
    global _loaded
    if _loaded:
        return
    _loaded = True
    from . import actions as _builtin_actions  # noqa: F401  (registers on import)
    from . import conditions as _builtin_conditions  # noqa: F401

    for group, registry in (("scenarioplay.actions", ACTIONS),
                            ("scenarioplay.conditions", CONDITIONS)):
        for ep in entry_points(group=group):
            cls = ep.load()
            registry[cls.KEYWORD] = cls
