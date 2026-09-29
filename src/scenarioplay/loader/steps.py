"""Turns raw step mappings into StepModel objects, reporting problems with line numbers."""

from __future__ import annotations

import difflib
from typing import Any

from pydantic import ValidationError

from ..conditions.base import Condition
from ..errors import Problem
from ..plugins import ACTIONS, CONDITIONS, FUTURE_CONDITIONS, FUTURE_STEPS
from .yaml_io import LocMap, YamlPath


def _fmt_loc(loc: tuple[Any, ...]) -> str:
    return ".".join(str(p) for p in loc)


def pydantic_problems(
    err: ValidationError, base: YamlPath, locs: LocMap, prefix: str = ""
) -> list[Problem]:
    problems = []
    for e in err.errors(include_url=False):
        loc = tuple(e["loc"])
        msg = e["msg"].removeprefix("Value error, ")
        if e["type"] == "extra_forbidden":
            msg = f"unknown option `{loc[-1]}`"
            where = _fmt_loc(loc[:-1])
        else:
            where = _fmt_loc(loc)
        text = f"{prefix}{where + ': ' if where else ''}{msg}"
        problems.append(Problem(text, locs.get(base + loc)))
    return problems


def parse_condition(
    raw: Any, path: YamlPath, locs: LocMap, problems: list[Problem]
) -> Condition | None:
    """Parse a wait condition. A bare string is shorthand for a regex condition."""
    if isinstance(raw, str):
        raw = {"regex": raw}
    if not isinstance(raw, dict):
        problems.append(Problem("a condition must be a mapping such as {prompt: true}",
                                locs.get(path)))
        return None
    kinds = [k for k in raw if k in CONDITIONS]
    if len(kinds) != 1:
        future = [k for k in raw if k in FUTURE_CONDITIONS]
        if future and not kinds:
            k = future[0]
            msg = (f"condition `{k}` is part of the scenario language but not implemented in "
                   f"this version (planned for phase {FUTURE_CONDITIONS[k]})")
        elif kinds:
            msg = f"a condition takes exactly one of {', '.join(sorted(CONDITIONS))}; " \
                  f"found {', '.join(kinds)}"
        else:
            msg = f"missing condition; expected one of: {', '.join(sorted(CONDITIONS))}"
        problems.append(Problem(msg, locs.get(path)))
        return None
    cls = CONDITIONS[kinds[0]]
    try:
        return cls.model_validate(raw)
    except ValidationError as e:
        problems.extend(pydantic_problems(e, path, locs, prefix=f"{path[-1]}: "))
        return None


def pick_keyword(raw: dict[str, Any]) -> tuple[str | None, str | None]:
    """Choose the step's keyword. Returns (keyword, error message)."""
    found = [k for k in raw if k in ACTIONS]
    if found:
        best = min(ACTIONS[k].PRIORITY for k in found)
        winners = [k for k in found if ACTIONS[k].PRIORITY == best]
        if len(winners) == 1:
            return winners[0], None
        return None, f"a step can hold only one action; found {', '.join(winners)}"
    future = [k for k in raw if k in FUTURE_STEPS]
    if future:
        k = future[0]
        return None, (f"`{k}` is part of the scenario language but not implemented in this "
                      f"version (planned for phase {FUTURE_STEPS[k]})")
    hints = []
    for key in raw:
        close = difflib.get_close_matches(str(key), ACTIONS, n=1)
        if close:
            hints.append(f"`{key}` (did you mean `{close[0]}`?)")
    known = ", ".join(sorted(ACTIONS))
    if hints:
        return None, f"unknown action {hints[0]}"
    keys = ", ".join(f"`{k}`" for k in raw) or "nothing"
    return None, f"the step has no action (found {keys}); known actions: {known}"


def parse_steps(raw_steps: list[Any], base: YamlPath, locs: LocMap,
                problems: list[Problem]) -> list[Any]:
    steps = []
    for i, raw in enumerate(raw_steps):
        path = base + (i,)
        if not isinstance(raw, dict):
            problems.append(Problem('a step must be a mapping, for example `- run: "ls"`',
                                    locs.get(path)))
            continue
        keyword, error = pick_keyword(raw)
        if keyword is None:
            problems.append(Problem(error or "invalid step", locs.get(path)))
            continue
        cls = ACTIONS[keyword]
        try:
            step = cls.model_validate(raw)
        except ValidationError as e:
            problems.extend(pydantic_problems(e, path, locs, prefix=f"{keyword}: "))
            continue
        step._path = path
        step._loc = locs.get(path)
        for field in cls.CONDITION_FIELDS:
            value = raw.get(field)
            if value is None:
                continue
            cond = parse_condition(value, path + (field,), locs, problems)
            if cond is not None:
                step._conditions[field] = cond
        steps.append(step)
    return steps
