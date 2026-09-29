"""`run --dry-run`: print the plan without touching the target."""

from __future__ import annotations

from typing import Any

from ..lang import Node
from ..loader import ParsedScenario


def _check_text(check: Any) -> str:
    if isinstance(check, Node):
        return "<expression>"
    return check.describe()


def _steps(lines: list[str], steps: list[Any], indent: int) -> None:
    pad = "  " * indent
    for i, step in enumerate(steps, start=1):
        where = f"  line {step.loc.line}" if step.loc else ""
        extras = []
        if step.console:
            extras.append(f"[{step.console}]")
        if step.label:
            extras.append(f"({step.label})")
        if step.when is not None:
            extras.append(f"when {step.when}")
        extra = (" " + " ".join(extras)) if extras else ""
        lines.append(f"{pad}{i:3}. {step.summary()}{extra}{where}")
        wait = step.conditions.get("wait_for") or step.conditions.get("expect")
        if wait is not None and step.KEYWORD != "wait_for":
            lines.append(f"{pad}       then wait for {wait.describe()}")
        elif step.KEYWORD == "run":
            lines.append(f"{pad}       then wait for the shell prompt")
        for field, children in step.children():
            lines.append(f"{pad}     {field}:")
            _steps(lines, children, indent + 3)


def format_plan(parsed: ParsedScenario) -> str:
    m = parsed.model
    lines = [f"Scenario: {parsed.title} ({parsed.file})",
             f"Target:   {m.target.kind}, recording {m.target.record}",
             "Consoles: " + ", ".join(f"{c.name} ({c.shell}, cwd {c.cwd})" for c in m.consoles)]
    if m.vars:
        lines.append("Vars:     " + ", ".join(f"{k}={v!r}" for k, v in m.vars.items()))
    rules = [("all consoles", r) for r in m.defaults.answers] + \
            [(f"console {c.name}", r) for c in m.consoles for r in c.answers]
    for where, rule in rules:
        answer = f"secret {rule.secret}" if rule.secret else repr(rule.text)
        enter = " + Enter" if rule.enter else ""
        lines.append(f"Answer:   /{rule.when}/ -> {answer}{enter} ({where})")
    for section in ("setup", "steps", "finally"):
        steps = parsed.sections.get(section, [])
        if not steps:
            continue
        lines.append("")
        lines.append({"setup": "Setup (not recorded):", "steps": "Steps:",
                      "finally": "Finally (not recorded):"}[section])
        _steps(lines, steps, 0)
    return "\n".join(lines)
