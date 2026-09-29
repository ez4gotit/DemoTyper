from __future__ import annotations

import pytest

from scenarioplay.errors import EnvironmentProblem
from scenarioplay.secretstore import load_secrets, referenced_secrets


def test_referenced_secrets(load):
    parsed, problems = load("""
        defaults:
          answers:
            - {when: 'password for', secret: SUDO_PASS}
            - {when: '\\[Y/n\\]', text: "y"}
        consoles:
          - name: main
            answers: [{when: 'Passphrase', secret: KEY_PASS}]
        steps:
          - secret: DB_PASS
            enter: true
    """)
    assert parsed is not None, [p.format() for p in problems]
    assert referenced_secrets(parsed) == {"SUDO_PASS", "KEY_PASS", "DB_PASS"}


def test_answer_rule_needs_exactly_one_answer(load):
    parsed, problems = load("""
        defaults:
          answers: [{when: 'x', secret: A, text: "y"}]
        steps: [{run: ls}]
    """)
    assert parsed is None and "exactly one of `secret` or `text`" in problems[0].message
    assert problems[0].loc.line == 2


def test_secret_names_are_identifiers(load):
    parsed, problems = load("""
        steps:
          - secret: "my password"
    """)
    assert parsed is None and problems[0].loc.line == 2


def test_secrets_rejected_in_captions_chapters_logs(load):
    parsed, problems = load("""
        steps:
          - chapter: "Password is {{ secret.SUDO_PASS }}"
          - caption: "{{secret.X}}"
          - log: "pw {{ secret.X }}"
    """)
    assert parsed is None
    lines = sorted(p.loc.line for p in problems if p.severity == "error")
    assert lines == [2, 3, 4]


def test_load_secrets_file_wins_over_env(tmp_path, monkeypatch):
    f = tmp_path / "s.yaml"
    f.write_text("A: from-file\n")
    f.chmod(0o600)
    monkeypatch.setenv("A", "from-env")
    monkeypatch.setenv("B", "env-only")
    logs = []
    values = load_secrets({"A", "B"}, f, lambda *a: logs.append(a))
    assert values == {"A": "from-file", "B": "env-only"}
    assert logs == []


def test_load_secrets_missing_and_empty(monkeypatch):
    monkeypatch.delenv("NOPE", raising=False)
    monkeypatch.setenv("EMPTY", "")
    with pytest.raises(EnvironmentProblem, match="missing secrets EMPTY, NOPE"):
        load_secrets({"NOPE", "EMPTY"}, None, lambda *a: None)


def test_load_secrets_bad_file(tmp_path):
    f = tmp_path / "s.yaml"
    f.write_text("- just\n- a list\n")
    with pytest.raises(EnvironmentProblem, match="mapping"):
        load_secrets({"A"}, f, lambda *a: None)
