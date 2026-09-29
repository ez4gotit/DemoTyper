"""`run --dry-run`: print the resolved plan without touching the target."""

from __future__ import annotations

from ..loader import ParsedScenario


def format_plan(parsed: ParsedScenario) -> str:
    m = parsed.model
    lines = [f"Scenario: {parsed.title} ({parsed.file})",
             f"Target:   {m.target.kind}, recording {m.target.record}",
             "Consoles: " + ", ".join(f"{c.name} ({c.shell}, cwd {c.cwd})" for c in m.consoles)]
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
        for i, step in enumerate(steps, start=1):
            where = f"line {step.loc.line}" if step.loc else ""
            console = f" [{step.console}]" if step.console else ""
            label = f" ({step.label})" if step.label else ""
            lines.append(f"  {i:3}. {step.summary()}{console}{label}  {where}")
            wait = step.conditions.get("wait_for") or step.conditions.get("expect")
            if wait is not None and step.KEYWORD != "wait_for":
                lines.append(f"       then wait for {wait.describe()}")
            elif step.KEYWORD == "run":
                lines.append("       then wait for the shell prompt")
    return "\n".join(lines)
