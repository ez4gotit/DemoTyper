"""`run --from X --to Y` (spec 11): run only part of the top-level steps.

X and Y name a step `label` or a chapter title. `--to` a chapter includes that whole
chapter (up to the next chapter); `--to` a label includes that step. `setup` and `finally`
always run, and `define` blocks are available everywhere.
"""

from __future__ import annotations

from typing import Any


def _names(step: Any) -> list[str]:
    names = []
    if step.label:
        names.append(step.label)
    if step.KEYWORD == "chapter":
        names.append(step.chapter)
    return names


def available(steps: list[Any]) -> list[str]:
    return [name for step in steps for name in _names(step)]


def _find(steps: list[Any], name: str) -> int | None:
    for i, step in enumerate(steps):
        if name in _names(step):
            return i
    return None


def select(steps: list[Any], start: str | None, end: str | None) -> tuple[int, int]:
    """Indexes [first, stop) of the steps to run. Raises ValueError for unknown names."""
    first, stop = 0, len(steps)
    known = ", ".join(repr(n) for n in available(steps)) or "none (add `label:` to steps)"
    if start is not None:
        index = _find(steps, start)
        if index is None:
            raise ValueError(f"--from {start!r}: no step label or chapter with that name "
                             f"(available: {known})")
        first = index
    if end is not None:
        index = _find(steps, end)
        if index is None:
            raise ValueError(f"--to {end!r}: no step label or chapter with that name "
                             f"(available: {known})")
        if steps[index].KEYWORD == "chapter" and end == steps[index].chapter:
            nxt = next((j for j in range(index + 1, len(steps))
                        if steps[j].KEYWORD == "chapter"), len(steps))
            stop = nxt
        else:
            stop = index + 1
        if stop <= first:
            raise ValueError(f"--to {end!r} comes before --from {start!r}")
    return first, stop
