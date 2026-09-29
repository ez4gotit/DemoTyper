"""The `scenarioplay` command (spec section 11)."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import click

from . import __version__
from .exitcodes import ExitCode
from .loader import load_scenario


def _load_or_exit(file: Path, *, quiet_ok: bool = False):
    parsed, problems = load_scenario(file)
    for p in problems:
        color = "red" if p.severity == "error" else "yellow"
        click.secho(p.format(), fg=color, err=True)
    if parsed is None:
        n = sum(1 for p in problems if p.severity == "error")
        click.secho(f"{file}: {n} error{'s' if n != 1 else ''}", fg="red", err=True)
        sys.exit(ExitCode.VALIDATION)
    return parsed


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="scenarioplay")
def main() -> None:
    """Play typing scenarios into real terminals and record the screen."""


@main.command()
@click.argument("file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def validate(file: Path) -> None:
    """Check a scenario: syntax, schema, console names, key names, regexes."""
    parsed = _load_or_exit(file)
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
def run(file: Path, dry_run: bool, no_record: bool, headless: bool, speed: float,
        out_dir: Path, display: str | None, size: str, typos_rate: float | None,
        no_typos: bool, secrets_file: Path | None, keep_session: bool,
        verbose: bool) -> None:
    """Play a scenario and record a take."""
    parsed = _load_or_exit(file)
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
                      no_typos=no_typos, secrets_file=secrets_file)
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
