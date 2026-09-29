"""Secret values (spec 5.1, 12): read from a secrets file or the environment, never logged."""

from __future__ import annotations

import os
import stat
from collections.abc import Callable
from pathlib import Path

from ruamel.yaml import YAML

from .errors import EnvironmentProblem
from .loader import ParsedScenario


def referenced_secrets(parsed: ParsedScenario) -> set[str]:
    """Every secret name the scenario can use: `secret` steps, answer rules and
    {{ secret.NAME }} in templates and expressions."""
    from .loader.steps import walk

    names: set[str] = set(parsed.template_secrets)
    model = parsed.model
    for rule in [*model.defaults.answers, *(r for c in model.consoles for r in c.answers)]:
        if rule.secret:
            names.add(rule.secret)
    for steps in parsed.sections.values():
        for step in walk(steps):
            if step.KEYWORD == "secret":
                names.add(step.secret)
    return names


def load_secrets(names: set[str], secrets_file: Path | None,
                 log: Callable[[str, str], None]) -> dict[str, str]:
    """Resolve each name from the secrets file first, then the environment."""
    from_file: dict[str, str] = {}
    if secrets_file is not None:
        try:
            data = YAML(typ="safe").load(secrets_file.read_text(encoding="utf-8"))
        except OSError as e:
            raise EnvironmentProblem(f"cannot read secrets file {secrets_file}: {e.strerror}")\
                from None
        except Exception as e:
            raise EnvironmentProblem(f"secrets file {secrets_file} is not valid YAML: {e}")\
                from None
        if data is None:
            data = {}
        if not isinstance(data, dict):
            raise EnvironmentProblem(f"secrets file {secrets_file} must be a mapping of "
                                     "NAME: value")
        from_file = {str(k): str(v) for k, v in data.items() if v is not None}
        mode = secrets_file.stat().st_mode
        if mode & (stat.S_IRGRP | stat.S_IROTH):
            log("warning", f"secrets file {secrets_file} is readable by other users; "
                           f"run: chmod 600 {secrets_file}")

    values: dict[str, str] = {}
    missing = []
    for name in sorted(names):
        value = from_file.get(name, os.environ.get(name))
        if not value:
            missing.append(name)
        else:
            values[name] = value
    if missing:
        where = f"the secrets file {secrets_file} or " if secrets_file else "a --secrets file or "
        raise EnvironmentProblem(
            f"missing secret{'s' if len(missing) > 1 else ''} {', '.join(missing)}: put "
            f"{'them' if len(missing) > 1 else 'it'} in {where}the environment")
    return values
