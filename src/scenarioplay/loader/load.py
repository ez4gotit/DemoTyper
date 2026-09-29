"""Entry point of the loader: file -> ParsedScenario plus a list of problems."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ..errors import Problem, ScenarioInvalid
from ..plugins import load_plugins
from .checks import Checker
from .model import ConsoleSpec, Defaults, Scenario, TargetSpec
from .steps import parse_steps, pydantic_problems
from .yaml_io import LocMap, load_yaml

SECTIONS = ("setup", "steps", "finally")


@dataclass
class ParsedScenario:
    file: Path
    raw: dict[str, Any]
    model: Scenario
    locs: LocMap
    sections: dict[str, list[Any]]  # section name -> list[StepModel]

    @property
    def title(self) -> str:
        return self.model.meta.title or self.file.stem


def load_scenario(path: Path) -> tuple[ParsedScenario | None, list[Problem]]:
    """Load and validate a scenario. Returns (scenario or None, problems).

    The scenario is None when any problem has severity "error".
    """
    load_plugins()
    try:
        raw, locs = load_yaml(path)
    except ScenarioInvalid as e:
        return None, e.problems

    if not isinstance(raw, dict):
        return None, [Problem("the scenario must be a YAML mapping with a `steps` list",
                              locs.get(()))]

    problems: list[Problem] = []
    try:
        model = Scenario.model_validate(raw)
    except ValidationError as e:
        problems.extend(pydantic_problems(e, (), locs))
        # Keep going with the steps so one run reports as much as possible.
        model = None

    sections: dict[str, list[Any]] = {}
    for name in SECTIONS:
        value = raw.get(name, [])
        if isinstance(value, list):
            sections[name] = parse_steps(value, (name,), locs, problems)

    checker = Checker(model or _fallback_model(raw), locs, problems)
    if model is not None:
        checker.check_scenario()
    for steps in sections.values():
        checker.check_steps(steps)

    problems.sort(key=lambda p: (p.loc.line if p.loc else 0, p.loc.col if p.loc else 0))
    if model is None or any(p.severity == "error" for p in problems):
        return None, problems
    return ParsedScenario(path, raw, model, locs, sections), problems


def _fallback_model(raw: dict[str, Any]) -> Scenario:
    """A stand-in when the top level is invalid, so step checks still run and one
    `validate` reports as many problems as possible. Keeps the consoles that are valid."""
    consoles = []
    for item in raw.get("consoles") or []:
        try:
            consoles.append(ConsoleSpec.model_validate(item))
        except ValidationError:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                consoles.append(ConsoleSpec.model_construct(name=item["name"]))
    return Scenario.model_construct(
        consoles=consoles or [ConsoleSpec(name="main")], defaults=Defaults(),
        target=TargetSpec(), steps=[], setup=[], finally_=[], vars={}, layout="single")
