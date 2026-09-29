"""Whole takes against a real tmux and bash, headless (no display, no recording)."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time

import pytest

from scenarioplay.console.driver import Console
from scenarioplay.exitcodes import ExitCode

from .conftest import FAST

pytestmark = pytest.mark.integration


async def test_every_character_arrives_exactly(play, tmp_path):
    target = tmp_path / "chars.txt"
    text = "| ~ $HOME { } \\ ; & < > \" ` # ! @ % ^ * ( ) [ ] ? , . : = + - _ / Юникод ёЁ ü ;"
    command = f"printf '%s\\n' '{text}' > {target}"
    # A JSON string is a valid YAML double-quoted scalar, so the escaping is exact.
    r = await play(f"""
steps:
  - run: {json.dumps(command, ensure_ascii=False)}
""")
    assert r.code == ExitCode.OK, r.log
    assert target.read_text(encoding="utf-8") == text + "\n"
    assert r.report["executed_mismatches"] == []


async def test_check_exit_failure_leaves_evidence(play):
    r = await play("""
steps:
  - run: "echo before"
  - run: "ls /definitely/not/here"
    check_exit: true
  - run: "echo never"
""")
    assert r.code == ExitCode.STEP_FAILED
    failure = r.report["failure"]
    assert failure["step"] == "steps.1" and failure["line"] == 8
    assert "exited with code 2" in failure["error"]
    assert any("No such file" in line for line in failure["last_output"])
    assert "echo never" not in r.transcript
    statuses = [s["status"] for s in r.report["steps"]]
    assert statuses == ["ok", "failed"]


async def test_expect_timeout_fails_and_on_fail_continue(play):
    r = await play("""
steps:
  - run: "echo hello"
    expect: {text: "goodbye", timeout: 1}
""")
    assert r.code == ExitCode.STEP_FAILED
    assert "timed out after 1s" in r.report["failure"]["error"]
    assert r.report["failure"]["expected"] == "text 'goodbye'"

    for d in (r.dir.parent).iterdir():
        shutil.rmtree(d)
    r = await play("""
steps:
  - run: "echo hello"
    expect: {text: "goodbye", timeout: 1}
    on_fail: continue
  - run: "echo after"
""")
    assert r.code == ExitCode.OK
    assert [s["status"] for s in r.report["steps"]] == ["failed-continued", "ok"]


async def test_since_last_input_ignores_the_command_echo(play):
    # The text "marker" is in the typed command itself; only real output may match.
    r = await play("""
steps:
  - run: "true marker"
    expect: {text: "marker", timeout: 1}
""")
    assert r.code == ExitCode.STEP_FAILED


async def test_wrong_prompt_regex_is_an_environment_error(play):
    r = await play("""
defaults: {prompt: "NEVER-MATCHES>$"}
steps: [{run: "ls"}]
""", fast=False)
    assert r.code == ExitCode.ENVIRONMENT
    assert "prompt regex" in r.report["failure"]["error"]


async def test_setup_is_cleared_and_finally_runs_after_failure(play, tmp_path):
    marker = tmp_path / "finally-ran"
    r = await play(f"""
setup:
  - run: "echo SETUP-OUTPUT"
steps:
  - run: "false"
    check_exit: true
finally:
  - run: "touch {marker}"
""")
    assert r.code == ExitCode.STEP_FAILED
    assert marker.exists()
    first_lines = r.transcript.splitlines()[:2]
    assert not any("SETUP-OUTPUT" in line for line in first_lines), r.transcript


async def test_multiline_type_and_keys(play):
    r = await play("""
steps:
  - type: "echo one\\necho two"
    enter: true
    enter_newlines: true
    wait_for: {regex: "^two$"}
  - type: "sleep 30"
    enter: true
  - pause: 0.5
  - key: C-c
    wait_for: {prompt: true, timeout: 5}
  - run: "echo done"
    expect: '^done$'
""")
    assert r.code == ExitCode.OK, r.log
    assert "^C" in r.transcript


async def test_verifier_repairs_a_dropped_keystroke(play, monkeypatch, tmp_path):
    """Spec 6.2: whatever goes wrong while typing, the command line is checked before Enter
    and fixed, so the shell never runs a wrong command."""
    original = Console.send_char
    sent = {"n": 0}

    async def flaky(self, ch):
        sent["n"] += 1
        if sent["n"] == 4:  # drop the 4th keystroke of the take
            return
        await original(self, ch)

    monkeypatch.setattr(Console, "send_char", flaky)
    target = tmp_path / "ok.txt"
    r = await play(f"""
steps:
  - run: "echo verified > {target}"
""")
    assert r.code == ExitCode.OK, r.log
    assert target.read_text() == "verified\n"
    assert "retyping" in r.log
    assert r.report["executed_mismatches"] == []


async def test_typos_are_switched_off_off_the_shell_prompt(play):
    r = await play("""
defaults:
  typing: {profile: robot, typos: {enabled: true, rate: 0.5}}
  after_command_pause: 0
steps:
  - type: "read answer"
    enter: true
  - type: "y"
    enter: true
  - run: "echo $answer"
    expect: '^y$'
""", fast=False)
    assert r.code == ExitCode.OK, r.log
    notes = [s["notes"] for s in r.report["steps"]]
    assert notes[1] == ["typos auto-off: not at a shell prompt"]


@pytest.mark.skipif(not shutil.which("zsh"), reason="zsh not installed")
async def test_zsh_console(play):
    r = await play("""
consoles: [{name: main, shell: zsh}]
defaults:
  typing: {profile: robot}
  after_command_pause: 0
  timeout: 15
  prompt: "[%#$>] ?$"
steps:
  - run: "false"
    check_exit: true
    on_fail: continue
  - run: "echo zsh-ok"
    expect: "^zsh-ok$"
""", fast=False)
    assert r.code == ExitCode.OK, r.log
    assert r.report["steps"][0]["status"] == "failed-continued"


def test_ctrl_c_interrupts_and_finalizes(write_scenario, tmp_path):
    path = write_scenario(FAST + """
steps:
  - run: "sleep 60"
    timeout: 120
""")
    out = tmp_path / "takes"
    proc = subprocess.Popen(
        [sys.executable, "-m", "scenarioplay.cli", "run", str(path), "--headless",
         "--out", str(out)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env={**os.environ, "PYTHONUNBUFFERED": "1"})
    deadline = time.time() + 20
    while time.time() < deadline:
        logs = list(out.glob("*/take.log"))
        if (logs and "waiting" in logs[0].read_text()) or \
                (logs and "step steps.0" in logs[0].read_text()):
            break
        time.sleep(0.2)
    time.sleep(1.5)
    proc.send_signal(signal.SIGINT)
    proc.wait(timeout=30)
    assert proc.returncode == ExitCode.INTERRUPTED
    report = json.loads(next(out.glob("*/report.json")).read_text())
    assert report["status"] == "interrupted"
    assert report["steps"][0]["status"] == "interrupted"
