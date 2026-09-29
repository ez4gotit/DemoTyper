"""Entry point of the loader: file -> ParsedScenario plus a list of problems."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ..errors import Problem, ScenarioInvalid
from ..plugins import load_plugins
from .checks import Checker
from .model import ConsoleSpec, Defaults, Scenario, TargetSpec
from .steps import StepParser, pydantic_problems
from .yaml_io import LocMap, load_yaml

SECTIONS = ("setup", "steps", "finally")


@dataclass
class ParsedScenario:
    file: Path
    raw: dict[str, Any]
    model: Scenario
    locs: LocMap
    sections: dict[str, list[Any]]  # section name -> list[StepModel]
    defines: dict[str, Any] = field(default_factory=dict)
    # `secret.NAME` names used in templates and expressions.
    template_secrets: set[str] = field(default_factory=set)

    @property
    def title(self) -> str:
        return self.model.meta.title or self.file.stem


def load_scenario(path: Path, extra_vars: Iterable[str] | None = None
                  ) -> tuple[ParsedScenario | None, list[Problem]]:
    """Load and validate a scenario. Returns (scenario or None, problems).

    `extra_vars` are the names given with --var / --vars. When None (a plain `validate`),
    variables that are not declared are warnings; otherwise they are errors.
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
    model: Scenario | None
    try:
        model = Scenario.model_validate(raw)
    except ValidationError as e:
        problems.extend(pydantic_problems(e, (), locs))
        # Keep going with the steps so one run reports as much as possible.
        model = None

    parser = StepParser(path, locs, problems)
    sections: dict[str, list[Any]] = {}
    for name in SECTIONS:
        value = raw.get(name, [])
        if isinstance(value, list):
            sections[name] = parser.parse_steps(value, (name,))

    checker = Checker(model or _fallback_model(raw), locs, problems, parser.defines,
                      None if extra_vars is None else set(extra_vars))
    if model is not None:
        checker.check_scenario()
    checker.assigned_names(sections)
    for name, steps in sections.items():
        checker.check_section(name, steps)

    problems.sort(key=lambda p: (p.loc.file if p.loc else "", p.loc.line if p.loc else 0,
                                 p.loc.col if p.loc else 0))
    if model is None or any(p.severity == "error" for p in problems):
        return None, problems
    return ParsedScenario(path, raw, model, locs, sections, parser.defines,
                          checker.secret_refs), problems


def resolve_includes(value: Any, file: Path) -> Any:
    """The raw scenario with every `- include: path` replaced by that file's steps (for
    scenario.resolved.yaml). The scenario was validated, so includes are known good."""
    if isinstance(value, dict):
        return {k: resolve_includes(v, file) for k, v in value.items()}
    if isinstance(value, list):
        out = []
        for item in value:
            if isinstance(item, dict) and set(item) == {"include"}:
                target = (file.parent / item["include"]).resolve()
                data, _ = load_yaml(target)
                if isinstance(data, dict):
                    data = data.get("steps", [])
                out.extend(resolve_includes(data, target))
            else:
                out.append(resolve_includes(item, file))
        return out
    return value


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
    raw_vars = raw.get("vars") if isinstance(raw.get("vars"), dict) else {}
    return Scenario.model_construct(
        consoles=consoles or [ConsoleSpec(name="main")], defaults=Defaults(),
        target=TargetSpec(), steps=[], setup=[], finally_=[], vars=raw_vars, layout="single")
