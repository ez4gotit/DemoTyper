"""Semantic checks that go beyond field types (spec 11 `validate`, WP 2.7)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from ..errors import Problem
from ..lang import ExprError, Node, parse_template
from .model import Scenario
from .yaml_io import LocMap

if TYPE_CHECKING:
    from ..actions.base import StepModel
    from ..conditions.base import Condition

BUILTINS = frozenset({"env", "secret", "take", "last", "loop", "error"})
# Blocks that may carry `when` (spec 8.2); every action may.
WHEN_BLOCKS = frozenset({"break", "continue", "stop"})
_COMMON_SKIP = frozenset({"console", "label", "when", "on_fail", "timeout"})


def field_keys(model: Any) -> Iterator[tuple[str, str]]:
    """(python attribute, YAML key) for each field of a model."""
    for name, info in type(model).model_fields.items():
        yield name, info.alias or name


def _template_refs(value: Any, names: set[str], paths: set[str]) -> None:
    if isinstance(value, str):
        if "{{" in value:
            try:
                t = parse_template(value)
            except ExprError:
                return  # reported by the parser already
            names |= t.names()
            paths |= t.paths()
    elif isinstance(value, list):
        for v in value:
            _template_refs(v, names, paths)
    elif isinstance(value, dict):
        for v in value.values():
            _template_refs(v, names, paths)


def condition_refs(cond: Condition, names: set[str], paths: set[str]) -> None:
    for name, key in field_keys(cond):
        if name in cond.NO_RENDER or key in ("any", "all"):
            continue
        _template_refs(getattr(cond, name), names, paths)
    for child in cond.children:
        condition_refs(child, names, paths)


def step_refs(step: StepModel) -> tuple[set[str], set[str]]:
    """Variables a step reads before running its nested steps: (root names, dotted paths)."""
    names: set[str] = set()
    paths: set[str] = set()
    skip = _COMMON_SKIP | step.NO_RENDER | set(step.CHECK_FIELDS) | \
        set(step.STEP_LIST_FIELDS) | set(step.CONDITION_FIELDS)
    for name, key in field_keys(step):
        if name in skip or key in skip:
            continue
        _template_refs(getattr(step, name), names, paths)
    for check in step.checks.values():
        if isinstance(check, Node):
            names |= check.names()
            paths |= check.paths()
        else:
            condition_refs(check, names, paths)
    for cond in step.conditions.values():
        condition_refs(cond, names, paths)
    if hasattr(step, "_elifs"):
        for check, _ in step._elifs:
            if isinstance(check, Node):
                names |= check.names()
                paths |= check.paths()
            else:
                condition_refs(check, names, paths)
    return names, paths


class Checker:
    def __init__(self, scenario: Scenario, locs: LocMap, problems: list[Problem],
                 defines: dict[str, Any] | None = None, extra_vars: set[str] | None = None):
        self.scenario = scenario
        self.locs = locs
        self.problems = problems
        self.defines = defines or {}
        self.extra_vars = extra_vars
        self.console_names = {c.name for c in scenario.consoles}
        self.secret_refs: set[str] = set()
        self.globals = set(scenario.vars or {}) | (extra_vars or set()) | BUILTINS
        self._assigned: set[str] = set()
        self._reported: set[tuple[str, int | None]] = set()

    # --- reporting ---------------------------------------------------------------------

    def _loc(self, step: StepModel, field: str | None):
        if step.loc is None:
            return None
        if field is None:
            return step.loc
        # Look the field up relative to the step's own file position.
        line_map = self.locs if step.loc.file == self.locs.file else None
        if line_map is not None:
            found = line_map.get(_file_path(step) + (field,))
            if found is not None:
                return found
        return step.loc

    def error(self, step: StepModel, message: str, field: str | None = None) -> None:
        self.problems.append(Problem(f"{step.KEYWORD}: {message}", self._loc(step, field)))

    def warning(self, step: StepModel, message: str, field: str | None = None) -> None:
        self.problems.append(
            Problem(f"{step.KEYWORD}: {message}", self._loc(step, field), "warning"))

    def check_console(self, step: StepModel, name: str | None, field: str) -> None:
        if name is not None and name not in self.console_names:
            known = ", ".join(sorted(self.console_names))
            self.error(step, f"unknown console {name!r} (declared: {known})", field)

    # --- steps -------------------------------------------------------------------------

    def check_section(self, name: str, steps: list[StepModel]) -> None:
        self.check_steps(steps, frozenset(), in_loop=False)

    def assigned_names(self, sections: dict[str, list[StepModel]]) -> None:
        """Names given values at run time (`set`, `capture`, run's `capture`, exec's
        `capture`) anywhere in the scenario count as defined everywhere."""
        from .steps import walk

        assigned: set[str] = set()
        for steps in sections.values():
            for step in walk(steps):
                for attr in ("set", "capture"):
                    value = getattr(step, attr, None)
                    if isinstance(value, str) and step.KEYWORD in ("set", "capture", "run",
                                                                   "exec"):
                        assigned.add(value)
                    elif value is not None and hasattr(value, "name"):
                        assigned.add(value.name)
        self._assigned = assigned

    def check_steps(self, steps: list[StepModel], local: frozenset[str], *,
                    in_loop: bool) -> None:
        for step in steps:
            self._check_step(step, local, in_loop)

    def _check_step(self, step: StepModel, local: frozenset[str], in_loop: bool) -> None:
        self.check_console(step, step.console, "console")
        for field, cond in step.conditions.items():
            self._check_condition_consoles(step, cond, field)
        for field, check in step.checks.items():
            if not isinstance(check, Node):
                self._check_condition_consoles(step, check, field)
        if step.IS_BLOCK and step.when is not None and step.KEYWORD not in WHEN_BLOCKS:
            self.error(step, "`when` makes a single step conditional; for a block, wrap it in "
                             "`if:` ... `then:`", "when")
        if step.KEYWORD in ("break", "continue") and not in_loop:
            self.error(step, f"`{step.KEYWORD}` is only allowed inside a loop (for_each, "
                             "repeat, while, until)", step.KEYWORD)

        names, paths = step_refs(step)
        self.secret_refs |= {p.split(".")[1] for p in paths
                             if p.startswith("secret.") and p.count(".") >= 1}
        for missing in sorted(names - self.globals - local - self._assigned):
            if (missing, step.loc.line if step.loc else None) in self._reported:
                continue
            self._reported.add((missing, step.loc.line if step.loc else None))
            message = (f"variable '{missing}' is not declared in `vars` and never set; pass "
                       f"it with --var {missing}=...")
            if self.extra_vars is None:
                self.warning(step, message)
            else:
                self.error(step, message)
        step.check(self)

        for field, children in step.children():
            child_local = local | step.child_names(field.split(".")[0])
            nested_loop = in_loop or step.IS_LOOP
            if step.KEYWORD == "define":
                child_local = frozenset(step.child_names(field))
                nested_loop = False
            self.check_steps(children, frozenset(child_local), in_loop=nested_loop)

    def _check_condition_consoles(self, step: StepModel, cond: Condition, field: str) -> None:
        self.check_console(step, cond.console, field)
        for child in cond.children:
            self._check_condition_consoles(step, child, field)

    # --- scenario ----------------------------------------------------------------------

    def check_scenario(self) -> None:
        s = self.scenario
        top = self.locs
        if len(s.consoles) > 1:
            self.problems.append(Problem(
                "more than one console is not supported in this version (planned for phase 3)",
                top.get(("consoles", 1))))
        if s.layout != "single":
            self.problems.append(Problem(
                f"layout {s.layout!r} is not supported in this version (planned for phase 3)",
                top.get(("layout",))))
        for i, c in enumerate(s.consoles):
            if c.host:
                self.problems.append(Problem(
                    "consoles on another machine (`host`) are planned for phase 3",
                    top.get(("consoles", i, "host"))))
        if s.target.kind != "local":
            self.problems.append(Problem(
                "the vmware target is planned for phase 4; `run` will refuse this scenario",
                top.get(("target", "kind")), "warning"))


def _file_path(step: StepModel) -> tuple[Any, ...]:
    """The step's path within its own file (without an include prefix)."""
    path = step.path
    for i in range(len(path) - 1, -1, -1):
        if isinstance(path[i], str) and path[i].startswith("<"):
            return tuple(path[i + 1:])
    return tuple(path)
