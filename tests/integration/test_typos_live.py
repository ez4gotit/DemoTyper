"""Typo soak test (spec 15, typing realism): with auto-typos on, typos appear and are
corrected on screen, and no command is ever executed with a typo left in it.

The spec's full run is 50 takes x 50 commands: SP_SOAK_TAKES=50 SP_SOAK_COMMANDS=50 pytest ...
"""

from __future__ import annotations

import json
import os
import shutil

import pytest

from scenarioplay.exitcodes import ExitCode

pytestmark = pytest.mark.integration

TAKES = int(os.environ.get("SP_SOAK_TAKES", "2"))
COMMANDS = int(os.environ.get("SP_SOAK_COMMANDS", "20"))
TEMPLATES = [
    "echo token-{n} | tr a-z A-Z",
    "printf '%s\\n' \"value {n}: ok\"",
    "test -d /tmp && echo dir-{n}-exists",
    "echo $(( {n} * 7 )) sevens",
    "ls /nonexistent-{n} 2>/dev/null || echo missing-{n}",
    "echo '{{braces}} [brackets] ~tilde-{n}'",  # quoted: zsh would glob / expand these
]
EXPECTED = [
    "TOKEN-{n}", "value {n}: ok", "dir-{n}-exists", "{seven} sevens", "missing-{n}",
    "{{braces}} [brackets] ~tilde-{n}",
]


def scenario(shell: str) -> tuple[str, list[str]]:
    steps, expected = [], []
    for n in range(COMMANDS):
        t = n % len(TEMPLATES)
        command = TEMPLATES[t].format(n=n)
        steps.append(f"  - run: {json.dumps(command)}")  # JSON strings are valid YAML
        expected.append(EXPECTED[t].format(n=n, seven=n * 7))
    prompt = '\n  prompt: "[%#$>] ?$"' if shell == "zsh" else ""
    text = f"""
consoles: [{{name: main, shell: {shell}}}]
defaults:
  typing:
    profile: expert
    typos: {{rate: 0.12, max_per_line: 2, notice_after: [0, 3]}}
  after_command_pause: 0{prompt}
steps:
""" + "\n".join(steps) + "\n"
    return text, expected


@pytest.mark.parametrize("take", range(TAKES))
@pytest.mark.parametrize("shell", ["bash", "zsh"])
async def test_typos_are_corrected_before_every_enter(play, shell, take):
    if shell == "zsh" and not shutil.which("zsh"):
        pytest.skip("zsh not installed")
    text, expected = scenario(shell)
    r = await play(text, fast=False)
    assert r.code == ExitCode.OK, r.log
    typos = r.log.count("typo at ")
    assert typos > 0, "the typo rate should produce typos"
    assert r.report["executed_mismatches"] == []
    lines = [line.rstrip() for line in r.transcript.splitlines()]
    for want in expected:
        assert want in lines, f"missing output {want!r}"
