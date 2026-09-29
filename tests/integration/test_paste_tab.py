"""Tab autocomplete on `type`, and the `paste` action (pseudo-paste of a substring)."""

from __future__ import annotations

import pytest

from scenarioplay.exitcodes import ExitCode

pytestmark = pytest.mark.integration

FAST = """
defaults:
  typing: {profile: robot}
  after_command_pause: 0
  timeout: 15
"""


async def test_tab_autocompletes_a_path(play):
    r = await play(FAST + """
steps:
  - type: "cat /etc/hostn"
    tab: true
    expect: "hostname"
    enter: true
""", fast=False)
    assert r.code == ExitCode.OK, r.log
    # The prefix was Tab-completed to /etc/hostname and ran.
    assert "cat /etc/hostname" in r.transcript


async def test_paste_literal_and_buffer_and_template(play):
    r = await play("""
vars: {who: "Ada Lovelace"}
defaults:
  typing: {profile: robot}
  after_command_pause: 0
  timeout: 15
  buffers:
    blob: "QUJDREVGMTIzNDU2Nzg5MA=="
steps:
  - type: "echo b: "
  - paste: {buffer: blob}
    enter: true
    wait_for: {text: "b: QUJDREVGMTIzNDU2Nzg5MA=="}
  - type: "echo n: "
  - paste: "{{ who }}"
    enter: true
    wait_for: {text: "n: Ada Lovelace"}
  - run: "true"
""", fast=False)
    assert r.code == ExitCode.OK, r.log
    assert "b: QUJDREVGMTIzNDU2Nzg5MA==" in r.transcript
    assert "n: Ada Lovelace" in r.transcript
    assert any("pasted 24 characters instantly" in s for step in r.report["steps"]
               for s in step["notes"])


async def test_paste_is_one_send(play, monkeypatch):
    """A paste inserts the whole string in a single send, not one char at a time."""
    from scenarioplay.console.driver import Console

    calls = {"send_text": 0, "send_char": 0}
    orig_text, orig_char = Console.send_text, Console.send_char

    async def st(self, text):
        calls["send_text"] += 1
        await orig_text(self, text)

    async def sc(self, ch):
        calls["send_char"] += 1
        await orig_char(self, ch)

    monkeypatch.setattr(Console, "send_text", st)
    monkeypatch.setattr(Console, "send_char", sc)
    r = await play(FAST + """
steps:
  - type: "true "
  - paste: "abcdefghijklmnop"
    enter: true
""", fast=False)
    assert r.code == ExitCode.OK, r.log
    assert calls["send_text"] == 1        # the 16-char paste was one send
    # the 5-char `type: "true "` prefix used send_char; the paste added none
    assert calls["send_char"] == len("true ")


def test_paste_buffer_unknown_is_a_validation_error(load):
    parsed, problems = load("""
        defaults: {buffers: {known: x}}
        steps:
          - paste: {buffer: missing}
    """)
    assert parsed is None
    assert "no buffer 'missing'" in problems[0].message and "known" in problems[0].message


def test_tab_rejects_enter_newlines(load):
    parsed, problems = load("""
        steps:
          - type: "a\\nb"
            enter_newlines: true
            tab: true
    """)
    assert parsed is None
    assert any("can't be combined with `enter_newlines`" in p.message for p in problems)
