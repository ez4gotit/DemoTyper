from __future__ import annotations

from scenarioplay.loader import load_scenario

from ..conftest import FIXTURES, ROOT


def errors(problems):
    return [p for p in problems if p.severity == "error"]


def test_examples_are_valid():
    for path in sorted((ROOT / "examples").glob("*.yaml")):
        parsed, problems = load_scenario(path)
        assert parsed is not None, [p.format() for p in problems]
        assert not errors(problems)


def test_seeded_errors_have_line_numbers():
    """Phase 1 acceptance: validate catches seeded errors, each with its line number."""
    parsed, problems = load_scenario(FIXTURES / "seeded_errors.yaml")
    assert parsed is None
    found = {p.loc.line: p.message for p in errors(problems)}
    expected = {
        4: "greater than 0",        # defaults.timeout: -5
        7: "did you mean `pause`",  # pasue: 2
        9: "invalid regular expression",
        10: "unknown key",
        12: "unknown console 'side'",
        13: "Tab",
        15: "unknown option `enter`",
    }
    for line, fragment in expected.items():
        assert line in found, f"no error on line {line}; got {found}"
        assert fragment in found[line], f"line {line}: {found[line]!r}"


def test_minimal_scenario_defaults(load):
    parsed, problems = load("""
        steps:
          - run: "ls"
    """)
    assert parsed is not None and not problems
    m = parsed.model
    assert [c.name for c in m.consoles] == ["main"]
    assert m.target.kind == "local" and m.layout == "single"
    assert parsed.sections["steps"][0].KEYWORD == "run"


def test_all_ten_top_level_keys_accepted_and_others_rejected(load):
    parsed, problems = load("""
        version: 1
        meta: {title: t}
        target: {kind: local}
        defaults: {timeout: 5}
        layout: single
        consoles: [{name: main}]
        vars: {}
        setup: [{run: "true"}]
        steps: [{run: "ls"}]
        finally: [{run: "true"}]
    """)
    assert parsed is not None, [p.format() for p in problems]

    parsed, problems = load("""
        steps: [{run: ls}]
        stepz: []
    """)
    assert parsed is None
    assert any("unknown option `stepz`" in p.message and p.loc.line == 2 for p in problems)


def test_steps_required(load):
    parsed, problems = load("meta: {title: x}\n")
    assert parsed is None
    assert any("steps" in p.message for p in problems)


def test_yaml_syntax_error_has_line(load):
    parsed, problems = load("""
        steps:
          - run: "ls"
          - run: "unterminated
    """)
    assert parsed is None
    assert problems[0].loc is not None and problems[0].loc.line >= 3
    assert "YAML syntax" in problems[0].message


def test_duplicate_keys_rejected(load):
    parsed, problems = load("""
        steps:
          - run: "ls"
            run: "pwd"
    """)
    assert parsed is None
    assert problems and problems[0].loc.line in (2, 3)


def test_option_keywords_do_not_count_as_second_action(load):
    parsed, problems = load("""
        steps:
          - type: "y"
            enter: true
          - chapter: "One"
            caption: "sub"
          - enter: true
            wait_for: {prompt: true}
          - wait_for: {text: done}
          - caption: "standalone"
    """)
    assert parsed is not None, [p.format() for p in problems]
    kinds = [s.KEYWORD for s in parsed.sections["steps"]]
    assert kinds == ["type", "chapter", "enter", "wait_for", "caption"]


def test_two_actions_in_one_step(load):
    parsed, problems = load("""
        steps:
          - run: "ls"
            key: C-c
    """)
    assert parsed is None
    assert "only one action" in problems[0].message


def test_future_keywords_explain_phase(load):
    parsed, problems = load("""
        steps:
          - for_each: [a, b]
            steps: []
          - run: ls
            wait_for: {idle: 2}
    """)
    assert parsed is None
    messages = " ".join(p.message for p in problems)
    assert "phase 2" in messages and "for_each" in messages and "idle" in messages


def test_expect_string_is_regex(load):
    parsed, _ = load("""
        steps:
          - run: "apt install nginx"
            expect: '\\[Y/n\\]'
    """)
    cond = parsed.sections["steps"][0].post_wait
    assert cond.KEYWORD == "regex" and cond.regex == r"\[Y/n\]"


def test_wait_for_and_expect_together_rejected(load):
    parsed, problems = load("""
        steps:
          - run: ls
            expect: x
            wait_for: {text: y}
    """)
    assert parsed is None
    assert "either `wait_for` or `expect`" in problems[0].message


def test_newline_needs_enter_newlines(load):
    parsed, problems = load("""
        steps:
          - type: "line1\\nline2"
    """)
    assert parsed is None and "enter_newlines" in problems[0].message
    parsed, problems = load("""
        steps:
          - type: "line1\\nline2"
            enter_newlines: true
    """)
    assert parsed is not None


def test_phase1_limits(load):
    parsed, problems = load("""
        layout: tabs
        consoles: [{name: a}, {name: b}]
        steps: [{run: ls}]
    """)
    assert parsed is None
    text = " ".join(p.message for p in problems)
    assert "phase 3" in text


def test_templates_warn_but_validate(load):
    parsed, problems = load("""
        vars: {site: x}
        steps: [{run: "curl {{ site }}"}]
    """)
    assert parsed is not None
    assert [p.severity for p in problems] == ["warning"]


def test_check_exit_rejected_on_sh_console(load):
    parsed, problems = load("""
        consoles: [{name: main, shell: sh}]
        steps:
          - run: "false"
            check_exit: true
    """)
    assert parsed is None and "bash or zsh" in problems[0].message


def test_prompt_regex_checked(load):
    parsed, problems = load("""
        defaults: {prompt: "([$"}
        steps: [{run: ls}]
    """)
    assert parsed is None
    assert problems[0].loc.line == 1 and "regular expression" in problems[0].message
