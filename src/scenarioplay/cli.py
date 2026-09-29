"""The `scenarioplay` command (spec section 11)."""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any

import click
from ruamel.yaml import YAML

from . import __version__
from .exitcodes import ExitCode
from .loader import load_scenario


def _load_or_exit(file: Path, extra_vars: set[str] | None = None):
    parsed, problems = load_scenario(file, extra_vars)
    for p in problems:
        color = "red" if p.severity == "error" else "yellow"
        click.secho(p.format(), fg=color, err=True)
    if parsed is None:
        n = sum(1 for p in problems if p.severity == "error")
        click.secho(f"{file}: {n} error{'s' if n != 1 else ''}", fg="red", err=True)
        sys.exit(ExitCode.VALIDATION)
    return parsed


def _parse_vars(pairs: tuple[str, ...], vars_file: Path | None
                ) -> tuple[dict[str, Any], dict[str, Any]]:
    """--var name=value (the value is read as YAML: 3 is a number, true a boolean, [a, b] a
    list) and --vars file.yaml (a mapping)."""
    yaml = YAML(typ="safe")
    cli: dict[str, Any] = {}
    for pair in pairs:
        name, sep, value = pair.partition("=")
        if not sep or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise click.BadParameter(f"expected name=value, got {pair!r}", param_hint="--var")
        try:
            cli[name] = yaml.load(value) if value.strip() else ""
        except Exception:
            cli[name] = value
    from_file: dict[str, Any] = {}
    if vars_file is not None:
        data = yaml.load(vars_file.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise click.BadParameter("the file must be a mapping of name: value",
                                     param_hint="--vars")
        from_file = data
    return cli, from_file


var_options = [
    click.option("--var", "var_pairs", multiple=True, metavar="NAME=VALUE",
                 help="Set a variable (repeatable). Overrides the scenario's `vars`."),
    click.option("--vars", "vars_file", type=click.Path(exists=True, dir_okay=False,
                                                         path_type=Path),
                 help="YAML file of variables; overrides --var and the scenario's `vars`."),
]


def with_var_options(fn):
    for option in reversed(var_options):
        fn = option(fn)
    return fn


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="scenarioplay")
def main() -> None:
    """Play typing scenarios into real terminals and record the screen."""


@main.command()
@click.argument("file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@with_var_options
def validate(file: Path, var_pairs: tuple[str, ...], vars_file: Path | None) -> None:
    """Check a scenario: syntax, schema, variables, console names, key names, regexes.

    Without --var/--vars, variables that are neither declared nor set are warnings;
    with them, errors (as in `run`)."""
    cli_vars, file_vars = _parse_vars(var_pairs, vars_file)
    given = set(cli_vars) | set(file_vars) if (var_pairs or vars_file) else None
    parsed = _load_or_exit(file, given)
    from .secretstore import referenced_secrets

    counts = {s: len(v) for s, v in parsed.sections.items() if v}
    detail = ", ".join(f"{n} {s}" for s, n in counts.items())
    click.secho(f"{file}: OK ({detail})", fg="green")
    names = referenced_secrets(parsed)
    if names:
        click.echo(f"needs secrets: {', '.join(sorted(names))} "
                   "(from --secrets FILE or the environment)")


@main.command()
@click.argument("file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--dry-run", is_flag=True, help="Print the plan without touching the target.")
@click.option("--no-record", is_flag=True, help="Play without recording (rehearsal).")
@click.option("--headless", is_flag=True,
              help="No terminal window; implies --no-record. Attach with tmux to watch.")
@click.option("--speed", type=click.FloatRange(min=0.05), default=1.0, show_default=True,
              help="Scale typing delays and pauses (2 = twice as fast).")
@click.option("--out", "out_dir", type=click.Path(file_okay=False, path_type=Path),
              default=Path("takes"), show_default=True, help="Folder for take folders.")
@click.option("--display", help="X display to record and show the terminal on.")
@click.option("--size", default="160x45", show_default=True,
              help="Console size in headless mode, COLSxROWS.")
@click.option("--typos", "typos_rate", type=click.FloatRange(0, 1),
              help="Override the auto-typo rate.")
@click.option("--no-typos", is_flag=True, help="Turn auto-typos off.")
@click.option("--secrets", "secrets_file",
              type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help="YAML file of NAME: value secrets (otherwise read from the environment).")
@click.option("--keep-session", is_flag=True, help="Leave the tmux session running.")
@click.option("-v", "--verbose", is_flag=True, help="Debug log: every wait and poll.")
@with_var_options
def run(file: Path, dry_run: bool, no_record: bool, headless: bool, speed: float,
        out_dir: Path, display: str | None, size: str, typos_rate: float | None,
        no_typos: bool, secrets_file: Path | None, keep_session: bool,
        verbose: bool, var_pairs: tuple[str, ...], vars_file: Path | None) -> None:
    """Play a scenario and record a take."""
    cli_vars, file_vars = _parse_vars(var_pairs, vars_file)
    parsed = _load_or_exit(file, set(cli_vars) | set(file_vars))
    if dry_run:
        from .engine.plan import format_plan

        click.echo(format_plan(parsed))
        return
    try:
        cols, rows = (int(x) for x in size.lower().split("x"))
    except ValueError:
        raise click.BadParameter("expected COLSxROWS, for example 160x45",
                                 param_hint="--size") from None

    from .engine.context import RunOptions
    from .engine.take import run_take

    opts = RunOptions(record=not (no_record or headless), speed=speed, out_dir=out_dir,
                      keep_session=keep_session, verbose=verbose, headless=headless,
                      display=display, width=cols, height=rows, typos_rate=typos_rate,
                      no_typos=no_typos, secrets_file=secrets_file, cli_vars=cli_vars,
                      vars_file=file_vars)
    code = asyncio.run(run_take(parsed, opts))
    sys.exit(code)


@main.command()
def schema() -> None:
    """Print the JSON Schema of the scenario format (for editor autocompletion)."""
    from .loader.schema import build_schema

    click.echo(json.dumps(build_schema(), indent=2))


@main.command()
@click.option("--display", help="X display to check (default $DISPLAY).")
def doctor(display: str | None) -> None:
    """Check that tmux, ffmpeg, the display and a terminal emulator are ready."""
    from .doctor import run_checks

    failed = False
    for check in run_checks(display):
        if check.ok:
            mark, color = "ok  ", "green"
        elif check.required:
            mark, color, failed = "FAIL", "red", True
        else:
            mark, color = "warn", "yellow"
        click.echo(click.style(f"[{mark}] ", fg=color) + f"{check.name}: {check.detail}")
    sys.exit(ExitCode.ENVIRONMENT if failed else ExitCode.OK)


if __name__ == "__main__":
    main()
