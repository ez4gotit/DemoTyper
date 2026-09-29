"""Turns raw step mappings into StepModel objects, reporting problems with line numbers.

Handles nested step lists (blocks), checks (`when`, `if`, `while`, ...), wait conditions,
`on_fail` recovery steps, `include` (spliced in at load time) and template syntax.
"""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ..conditions.base import Condition
from ..errors import Problem, ScenarioInvalid
from ..lang import ExprError, parse_expression, parse_template
from ..plugins import ACTIONS, CONDITIONS, FUTURE_CONDITIONS, FUTURE_STEPS
from .yaml_io import LocMap, YamlPath, load_yaml


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
    for key in raw:
        close = difflib.get_close_matches(str(key), ACTIONS, n=1)
        if close:
            return None, f"unknown action `{key}` (did you mean `{close[0]}`?)"
    keys = ", ".join(f"`{k}`" for k in raw) or "nothing"
    return None, f"the step has no action (found {keys}); known actions: " \
                 f"{', '.join(sorted(ACTIONS))}"


class StepParser:
    """Parses the step lists of one file. Includes get their own parser, sharing problems,
    the include stack and the `define` registry."""

    def __init__(self, file: Path, locs: LocMap, problems: list[Problem],
                 defines: dict[str, Any] | None = None, stack: tuple[Path, ...] = (),
                 display_prefix: tuple[Any, ...] = ()):
        self.file = file
        self.locs = locs
        self.problems = problems
        self.defines = defines if defines is not None else {}
        self.stack = stack or (file.resolve(),)
        self.display_prefix = display_prefix

    def error(self, message: str, path: YamlPath) -> None:
        self.problems.append(Problem(message, self.locs.get(path)))

    # --- steps -------------------------------------------------------------------------

    def parse_steps(self, raw_steps: Any, base: YamlPath) -> list[Any]:
        if not isinstance(raw_steps, list):
            self.error("expected a list of steps", base)
            return []
        steps: list[Any] = []
        for i, raw in enumerate(raw_steps):
            path = base + (i,)
            if not isinstance(raw, dict):
                self.error('a step must be a mapping, for example `- run: "ls"`', path)
                continue
            if "include" in raw:
                steps.extend(self._include(raw, path))
                continue
            step = self.parse_step(raw, path)
            if step is not None:
                steps.append(step)
        return steps

    def parse_step(self, raw: dict[str, Any], path: YamlPath) -> Any:
        keyword, error = pick_keyword(raw)
        if keyword is None:
            self.error(error or "invalid step", path)
            return None
        cls = ACTIONS[keyword]
        try:
            step = cls.model_validate(raw)
        except ValidationError as e:
            self.problems.extend(pydantic_problems(e, path, self.locs, prefix=f"{keyword}: "))
            return None
        step._path = self.display_prefix + path
        step._loc = self.locs.get(path)
        for field in cls.CONDITION_FIELDS:
            if raw.get(field) is not None:
                cond = self.parse_condition(raw[field], path + (field,))
                if cond is not None:
                    step._conditions[field] = cond
        for field in ("when", *cls.CHECK_FIELDS):
            if raw.get(field) is not None:
                check = self.parse_check(raw[field], path + (field,))
                if check is not None:
                    step._checks[field] = check
        for field in cls.STEP_LIST_FIELDS:
            if raw.get(field) is not None:
                step._children[field] = self.parse_steps(raw[field], path + (field,))
        if hasattr(step, "parse_extra"):
            step.parse_extra(raw, path, self)
        if isinstance(raw.get("on_fail"), list):
            step._on_fail_steps = self.parse_steps(raw["on_fail"], path + ("on_fail",))
        self._check_templates(step, raw, path)
        if keyword == "define":
            self._register_define(step, path)
        return step

    def _check_templates(self, step: Any, raw: dict[str, Any], path: YamlPath) -> None:
        """Report {{ }} syntax errors now, with the line, instead of mid-take."""
        skip = {"console", "label", "when", "on_fail", *step.NO_RENDER, *step.CHECK_FIELDS,
                *step.STEP_LIST_FIELDS, *step.CONDITION_FIELDS}
        for key, value in raw.items():
            if key not in skip:
                self._template_errors(value, path + (key,))

    def _template_errors(self, value: Any, path: YamlPath) -> None:
        if isinstance(value, str):
            if "{{" in value:
                try:
                    parse_template(value)
                except ExprError as e:
                    self.error(f"template: {e}", path)
        elif isinstance(value, list):
            for i, v in enumerate(value):
                self._template_errors(v, path + (i,))
        elif isinstance(value, dict):
            for k, v in value.items():
                self._template_errors(v, path + (k,))

    def _register_define(self, step: Any, path: YamlPath) -> None:
        if step.define in self.defines:
            other = self.defines[step.define]
            where = f" (first defined at line {other.loc.line})" if other.loc else ""
            self.error(f"define: `{step.define}` is defined twice{where}", path + ("define",))
        else:
            self.defines[step.define] = step

    # --- checks and conditions ---------------------------------------------------------

    def parse_check(self, raw: Any, path: YamlPath) -> Any:
        """An expression string, a condition mapping, or true/false."""
        if isinstance(raw, bool):
            from ..lang.expr import Literal

            return Literal(raw)
        if isinstance(raw, str):
            try:
                return parse_expression(raw)
            except ExprError as e:
                hint = " (conditions are expressions: write `x == 1`, not `{{ x }} == 1`)" \
                    if "{{" in raw else ""
                self.error(f"{path[-1]}: invalid expression: {e}{hint}", path)
                return None
        if isinstance(raw, dict):
            cond = self.parse_condition(raw, path)
            if cond is not None and not cond.SINGLE_SHOT:
                self.error(f"{path[-1]}: `{cond.KEYWORD}` needs time to observe, so it cannot "
                           "be checked once; use it in `wait_for`", path)
            return cond
        self.error(f"{path[-1]}: expected an expression string or a condition mapping", path)
        return None

    def parse_condition(self, raw: Any, path: YamlPath) -> Condition | None:
        """Parse a wait condition. A bare string is shorthand for a regex condition."""
        if isinstance(raw, str):
            raw = {"regex": raw}
        if not isinstance(raw, dict):
            self.error("a condition must be a mapping such as {prompt: true}", path)
            return None
        kinds = [k for k in raw if k in CONDITIONS]
        if len(kinds) != 1:
            future = [k for k in raw if k in FUTURE_CONDITIONS]
            if future and not kinds:
                k = future[0]
                msg = (f"condition `{k}` is part of the scenario language but not implemented "
                       f"in this version (planned for phase {FUTURE_CONDITIONS[k]})")
            elif kinds:
                msg = (f"a condition takes exactly one of {', '.join(sorted(CONDITIONS))}; "
                       f"found {', '.join(kinds)}")
            else:
                msg = f"missing condition; expected one of: {', '.join(sorted(CONDITIONS))}"
            self.error(msg, path)
            return None
        cls = CONDITIONS[kinds[0]]
        try:
            cond = cls.model_validate(raw)
        except ValidationError as e:
            self.problems.extend(pydantic_problems(e, path, self.locs, prefix=f"{path[-1]}: "))
            return None
        if kinds[0] in ("any", "all"):
            items = raw[kinds[0]]
            if not items:
                self.error(f"`{kinds[0]}` needs at least one condition", path + (kinds[0],))
            for i, item in enumerate(items):
                child = self.parse_condition(item, path + (kinds[0], i))
                if child is not None:
                    cond._children.append(child)
        if isinstance(raw.get("on_timeout"), list):
            cond._on_timeout_steps = self.parse_steps(raw["on_timeout"], path + ("on_timeout",))
        for key, value in raw.items():
            if key not in cond.NO_RENDER and key not in ("any", "all", "as"):
                self._template_errors(value, path + (key,))
        return cond

    # --- include -----------------------------------------------------------------------

    def _include(self, raw: dict[str, Any], path: YamlPath) -> list[Any]:
        extra = [k for k in raw if k != "include"]
        if extra:
            self.error(f"include: unknown option `{extra[0]}` (an include takes only a path)",
                       path + (extra[0],))
        target = raw["include"]
        if not isinstance(target, str) or not target:
            self.error("include: expected a file path", path + ("include",))
            return []
        file = (self.file.parent / target).resolve()
        if file in self.stack:
            chain = " -> ".join(p.name for p in (*self.stack, file))
            self.error(f"include: circular include ({chain})", path + ("include",))
            return []
        try:
            data, locs = load_yaml(file)
        except ScenarioInvalid as e:
            for p in e.problems:
                if p.loc is None:
                    p.loc = self.locs.get(path + ("include",))
                    p.message = f"include {target}: {p.message}"
            self.problems.extend(e.problems)
            return []
        base: YamlPath = ()
        if isinstance(data, dict) and set(data) == {"steps"}:
            data, base = data["steps"], ("steps",)
        if not isinstance(data, list):
            self.error(f"include: {target} must hold a list of steps (or only `steps:`)",
                       path + ("include",))
            return []
        sub = StepParser(file, locs, self.problems, self.defines, (*self.stack, file),
                         self.display_prefix + path + (f"<{target}>",))
        return sub.parse_steps(data, base)


def parse_steps(raw_steps: list[Any], base: YamlPath, locs: LocMap,
                problems: list[Problem], file: Path | None = None,
                defines: dict[str, Any] | None = None) -> list[Any]:
    """Parse one top-level step list (setup, steps or finally)."""
    parser = StepParser(file or Path(locs.file), locs, problems, defines)
    return parser.parse_steps(raw_steps, base)


def walk(steps: list[Any]):
    """Every step, depth first, with its nested steps."""
    for step in steps:
        yield step
        for _, children in step.children():
            yield from walk(children)
