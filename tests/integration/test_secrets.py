"""Secrets and automatic answers against a real terminal.

`fakesudo` behaves like sudo: it prompts `[sudo] password for tester:` with echo off,
says `Sorry, try again.` on a wrong password and gives up after three attempts.
"""

from __future__ import annotations

import pytest

from scenarioplay.exitcodes import ExitCode

pytestmark = pytest.mark.integration

PASSWORD = "s3cr3t Пароль!#"
ENV = "SP_TEST_PASS"

FAST = """
defaults:
  typing: {profile: robot}
  after_command_pause: 0
  timeout: 10
"""

FAKESUDO = """#!/bin/bash
for try in 1 2 3; do
  read -r -s -p "[sudo] password for tester: " pw; echo
  if [ "$pw" = "$(cat '{expected}')" ]; then echo "AUTH-OK"; exit 0; fi
  echo "Sorry, try again."
done
echo "sudo: 3 incorrect password attempts"; exit 1
"""

ANSWERS = """
  answers:
    - when: '\\[sudo\\] password for'
      secret: SP_TEST_PASS
"""


@pytest.fixture
def fakesudo(tmp_path):
    expected = tmp_path / "expected"
    expected.write_text(PASSWORD, encoding="utf-8")
    script = tmp_path / "fakesudo"
    script.write_text(FAKESUDO.format(expected=expected))
    script.chmod(0o755)
    return script


def assert_secret_nowhere(result, value=PASSWORD):
    for path in result.dir.rglob("*"):
        if path.is_file():
            assert value.encode() not in path.read_bytes(), f"secret found in {path.name}"


async def test_sudo_password_answered_automatically(play, fakesudo, monkeypatch):
    monkeypatch.setenv(ENV, PASSWORD)
    r = await play(FAST + ANSWERS + f"""
steps:
  - run: "{fakesudo} && echo after"
    expect: '^after$'
""", fast=False)
    assert r.code == ExitCode.OK, r.log
    assert "AUTH-OK" in r.transcript and "Sorry" not in r.transcript
    notes = r.report["steps"][0]["notes"]
    assert notes == ["answering '[sudo] password for tester:' with secret SP_TEST_PASS"]
    assert_secret_nowhere(r)


async def test_wrong_password_fails_after_one_attempt(play, fakesudo, monkeypatch):
    monkeypatch.setenv(ENV, "wrong-password")
    r = await play(FAST + ANSWERS + f"""
steps:
  - run: "{fakesudo}"
""", fast=False)
    assert r.code == ExitCode.STEP_FAILED
    assert "was not accepted" in r.report["failure"]["error"]
    assert r.transcript.count("Sorry, try again.") == 1
    assert_secret_nowhere(r, "wrong-password")


async def test_secret_never_typed_into_an_echoing_prompt(play, tmp_path, monkeypatch):
    monkeypatch.setenv(ENV, PASSWORD)
    r = await play(FAST + ANSWERS + """
steps:
  - run: "read -r -p '[sudo] password for tester: ' visible"
    timeout: 2
""", fast=False)
    assert r.code == ExitCode.STEP_FAILED
    assert "timed out" in r.report["failure"]["error"]
    assert PASSWORD not in r.transcript
    assert_secret_nowhere(r)


async def test_explicit_secret_step(play, fakesudo, monkeypatch):
    monkeypatch.setenv(ENV, PASSWORD)
    r = await play(f"""
steps:
  - type: "{fakesudo}"
    enter: true
  - secret: SP_TEST_PASS
    enter: true
    wait_for: {{text: AUTH-OK}}
""")
    assert r.code == ExitCode.OK, r.log
    assert r.report["steps"][1]["summary"] == "secret: SP_TEST_PASS (****)"
    assert_secret_nowhere(r)


async def test_explicit_secret_refuses_echoing_terminal(play, monkeypatch):
    monkeypatch.setenv(ENV, PASSWORD)
    r = await play("""
steps:
  - type: "cat"
    enter: true
  - secret: SP_TEST_PASS
    timeout: 1
""")
    assert r.code == ExitCode.STEP_FAILED
    assert "still echoes" in r.report["failure"]["error"]
    assert_secret_nowhere(r)


async def test_secrets_file_and_text_answer(play, fakesudo, tmp_path, monkeypatch):
    monkeypatch.delenv(ENV, raising=False)
    secrets = tmp_path / "secrets.yaml"
    secrets.write_text(f'{ENV}: "{PASSWORD}"\n', encoding="utf-8")
    secrets.chmod(0o600)
    r = await play(FAST + ANSWERS + f"""
    - when: 'Continue\\? \\[Y/n\\]'
      text: "y"
steps:
  - run: "read -r -p 'Continue? [Y/n] ' a && echo answer=$a"
    expect: '^answer=y$'
  - run: "{fakesudo}"
    expect: AUTH-OK
""", fast=False, secrets_file=secrets)
    assert r.code == ExitCode.OK, r.log
    assert_secret_nowhere(r)


async def test_missing_secret_stops_before_starting(play, monkeypatch):
    monkeypatch.delenv(ENV, raising=False)
    r = await play(FAST + ANSWERS + """
steps: [{run: "echo hi"}]
""", fast=False)
    assert r.code == ExitCode.ENVIRONMENT
    assert "missing secret SP_TEST_PASS" in r.report["failure"]["error"]
    assert r.report["steps"] == []
