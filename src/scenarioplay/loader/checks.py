"""Semantic checks that go beyond field types (spec section 11, `validate`)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..errors import Problem
from .model import Scenario
from .yaml_io import LocMap

if TYPE_CHECKING:
    from ..actions.base import StepModel


class Checker:
    def __init__(self, scenario: Scenario, locs: LocMap, problems: list[Problem]):
        self.scenario = scenario
        self.locs = locs
        self.problems = problems
        self.console_names = {c.name for c in scenario.consoles}

    def _loc(self, step: StepModel, field: str | None):
        return self.locs.get(step.path + ((field,) if field else ()))

    def error(self, step: StepModel, message: str, field: str | None = None) -> None:
        self.problems.append(Problem(f"{step.KEYWORD}: {message}", self._loc(step, field)))

    def warning(self, step: StepModel, message: str, field: str | None = None) -> None:
        self.problems.append(
            Problem(f"{step.KEYWORD}: {message}", self._loc(step, field), "warning"))

    def check_console(self, step: StepModel, name: str | None, field: str) -> None:
        if name is not None and name not in self.console_names:
            known = ", ".join(sorted(self.console_names))
            self.error(step, f"unknown console {name!r} (declared: {known})", field)

    def check_steps(self, steps: list[StepModel]) -> None:
        for step in steps:
            self.check_console(step, step.console, "console")
            for field, cond in step.conditions.items():
                self.check_console(step, cond.console, field)
            if step.when is not None:
                self.error(step, "`when` is not implemented in this version (planned for "
                                 "phase 2)", "when")
            step.check(self)

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
        if s.vars or _has_template(s.setup) or _has_template(s.steps) or \
                _has_template(s.finally_):
            self.problems.append(Problem(
                "variables and {{ }} templates are planned for phase 2; in this version "
                "template text is typed literally", top.get(("vars",)) or top.get(("steps",)),
                "warning"))


def _has_template(value: Any) -> bool:
    if isinstance(value, str):
        return "{{" in value
    if isinstance(value, dict):
        return any(_has_template(v) for v in value.values())
    if isinstance(value, list):
        return any(_has_template(v) for v in value)
    return False
