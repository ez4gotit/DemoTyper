"""Loading and validating control blocks, variables and includes (phase 2)."""

from __future__ import annotations

from scenarioplay.loader import load_scenario
from scenarioplay.loader.steps import walk


def errors(problems):
    return [p for p in problems if p.severity == "error"]


def messages(problems):
    return " | ".join(p.message for p in problems)


def test_blocks_parse_into_a_tree(load):
    parsed, problems = load("""
        vars: {packages: [nginx, curl], mode: fast}
        steps:
          - if: "mode == 'fast'"
            then:
              - run: "echo fast"
            elif:
              - if: "mode == 'slow'"
                then: [{run: "echo slow"}]
            else:
              - run: "echo other"
          - for_each: "{{ packages }}"
            as: pkg
            steps:
              - run: "apt-cache policy {{ pkg }}"
              - break: true
                when: "loop.index > 1"
          - until: {regex: "HTTP/1.1 200"}
            max_iterations: 3
            steps: [{run: "curl -sI localhost"}]
    """)
    assert parsed is not None, messages(problems)
    kinds = [s.KEYWORD for s in walk(parsed.sections["steps"])]
    assert kinds == ["if", "run", "run", "run", "for_each", "run", "break", "until", "run"]
    if_step = parsed.sections["steps"][0]
    assert [name for name, _ in if_step.children()] == ["then", "else", "elif.0"]


def test_loop_limits_and_break_placement(load):
    parsed, problems = load("""
        steps:
          - while: "true"
            steps: [{run: ls}]
          - break: true
    """)
    assert parsed is None
    text = messages(problems)
    assert "max_iterations" in text
    assert "only allowed inside a loop" in text


def test_when_on_block_rejected_if_needs_then(load):
    parsed, problems = load("""
        steps:
          - repeat: 2
            when: "true"
            steps: [{run: ls}]
          - if: "true"
            else: [{run: ls}]
    """)
    assert parsed is None
    text = messages(problems)
    assert "wrap it in `if:`" in text
    assert "then" in text


def test_define_and_call_checks(load):
    parsed, problems = load("""
        steps:
          - define: create_user
            params: [name, shell]
            steps: [{run: "sudo useradd -m -s {{ shell }} {{ name }}"}]
          - call: create_user
            with: {name: alice}
          - call: create_usr
          - define: create_user
            steps: []
    """)
    assert parsed is None
    text = messages(problems)
    assert "missing parameter shell" in text
    assert "no `define: create_usr`" in text
    assert "defined twice" in text


def test_params_and_loop_vars_are_scoped(load):
    parsed, problems = load("""
        steps:
          - define: greet
            params: [who]
            steps: [{run: "echo {{ who }}"}]
          - call: greet
            with: {who: bob}
          - for_each: [a, b]
            as: letter
            steps: [{run: "echo {{ letter }} {{ loop.index }}"}]
          - run: "echo {{ letter }}"
    """)
    assert parsed is not None
    warnings = [p for p in problems if p.severity == "warning"]
    assert len(warnings) == 1 and "'letter'" in warnings[0].message
    assert warnings[0].loc.line == 10


def test_undefined_variables_warn_or_fail(write_scenario):
    path = write_scenario("""
        steps:
          - run: "curl {{ site }}"
          - set: later
            value: 1
          - run: "echo {{ later }}"
    """)
    parsed, problems = load_scenario(path)
    assert parsed is not None
    assert [p.severity for p in problems] == ["warning"]
    parsed, problems = load_scenario(path, extra_vars=set())
    assert parsed is None and "'site'" in errors(problems)[0].message
    parsed, problems = load_scenario(path, extra_vars={"site"})
    assert parsed is not None and problems == []


def test_template_and_expression_syntax_errors_have_lines(load):
    parsed, problems = load("""
        vars: {x: 1}
        steps:
          - run: "echo {{ x + }}"
          - if: "x =="
            then: [{run: ls}]
          - when: "{{ x }} == 1"
            run: ls
    """)
    assert parsed is None
    by_line = {p.loc.line: p.message for p in errors(problems)}
    assert "template" in by_line[3]
    assert "invalid expression" in by_line[4]
    assert "not `{{ x }} == 1`" in by_line[6]


def test_idle_cannot_be_checked_once(load):
    parsed, problems = load("""
        steps:
          - if: {idle: 2}
            then: [{run: ls}]
    """)
    assert parsed is None and "cannot be checked once" in messages(problems)


def test_include_splices_steps_and_reports_its_own_lines(write_scenario, tmp_path):
    (tmp_path / "common").mkdir()
    (tmp_path / "common" / "login.yaml").write_text(
        "- run: \"echo included\"\n- pasue: 1\n", encoding="utf-8")
    path = write_scenario("""
        steps:
          - run: "echo before"
          - include: common/login.yaml
    """)
    parsed, problems = load_scenario(path)
    assert parsed is None
    (problem,) = errors(problems)
    assert problem.loc.file.endswith("login.yaml") and problem.loc.line == 2

    (tmp_path / "common" / "login.yaml").write_text(
        "steps:\n  - run: \"echo included\"\n", encoding="utf-8")
    parsed, problems = load_scenario(path)
    assert parsed is not None, messages(problems)
    steps = parsed.sections["steps"]
    assert [s.run for s in steps] == ["echo before", "echo included"]
    assert "<common/login.yaml>" in steps[1].path_str()


def test_include_cycle(write_scenario, tmp_path):
    (tmp_path / "a.yaml").write_text("- include: b.yaml\n")
    (tmp_path / "b.yaml").write_text("- include: a.yaml\n")
    path = write_scenario("steps:\n  - include: a.yaml\n")
    parsed, problems = load_scenario(path)
    assert parsed is None and "circular include" in messages(problems)


def test_secret_references_are_collected_and_kept_off_screen(load):
    parsed, problems = load("""
        steps:
          - exec: "curl -u admin:{{ secret.API_TOKEN }} http://x"
    """)
    assert parsed is not None and parsed.template_secrets == {"API_TOKEN"}
    parsed, problems = load("""
        steps:
          - run: "mysql -p{{ secret.DB }}"
    """)
    assert parsed is None and "visible on screen" in messages(problems)


def test_on_fail_forms(load):
    parsed, problems = load("""
        defaults: {on_fail: {retry: 2, delay: 0}}
        steps:
          - run: "false"
            on_fail: continue
          - run: "flaky"
            on_fail: {retry: 3}
          - run: "risky"
            on_fail:
              - run: "echo recovering"
    """)
    assert parsed is not None, messages(problems)
    recovery = parsed.sections["steps"][2]._on_fail_steps
    assert [s.run for s in recovery] == ["echo recovering"]


def test_any_all_conditions_nest(load):
    parsed, problems = load("""
        steps:
          - wait_for:
              any:
                - {text: "password for", as: need_password}
                - all: [{prompt: true}, {file: /tmp/x}]
              timeout: 5
    """)
    assert parsed is not None, messages(problems)
    cond = parsed.sections["steps"][0].conditions["wait_for"]
    assert [c.KEYWORD for c in cond.children] == ["text", "all"]
    assert [c.KEYWORD for c in cond.children[1].children] == ["prompt", "file"]
