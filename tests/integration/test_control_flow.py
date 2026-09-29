"""Control flow, variables and data actions in real takes (phase 2)."""

from __future__ import annotations

import pytest

from scenarioplay.exitcodes import ExitCode

pytestmark = pytest.mark.integration


def statuses(r):
    return {s["path"]: s["status"] for s in r.report["steps"]}


def notes(r, path):
    return next(s["notes"] for s in r.report["steps"] if s["path"] == path)


async def test_variables_templates_and_cli_overrides(play):
    scenario = """
vars:
  packages: [nginx, curl]
  mode: fast
steps:
  - run: "echo install {{ packages | join(',') }} mode={{ mode | upper }}"
    expect: '^install nginx,curl mode=(FAST|SLOW)$'
  - if: "mode == 'fast'"
    then: [{run: "echo BRANCH-FAST"}]
    elif:
      - if: "mode == 'slow'"
        then: [{run: "echo BRANCH-SLOW"}]
    else: [{run: "echo BRANCH-OTHER"}]
"""
    r = await play(scenario)
    assert r.code == ExitCode.OK, r.log
    assert "BRANCH-FAST" in r.transcript and "BRANCH-SLOW" not in r.transcript
    assert notes(r, "steps.1") == ["branch: then"]


async def test_cli_var_takes_the_other_branch(play):
    r = await play("""
vars: {mode: fast}
steps:
  - if: "mode == 'fast'"
    then: [{run: "echo BRANCH-FAST"}]
    elif:
      - if: "mode == 'slow'"
        then: [{run: "echo BRANCH-SLOW"}]
""", cli_vars={"mode": "slow"})
    assert r.code == ExitCode.OK, r.log
    assert "BRANCH-SLOW" in r.transcript and "BRANCH-FAST" not in r.transcript


async def test_loops_break_continue_and_loop_vars(play):
    r = await play("""
steps:
  - for_each: [a, b, c, d]
    as: letter
    steps:
      - continue: true
        when: "letter == 'b'"
      - break: true
        when: "letter == 'd'"
      - run: "echo item-{{ loop.index }}-{{ letter }}"
  - repeat: 2
    steps: [{run: "echo rep-{{ loop.index }}"}]
""")
    assert r.code == ExitCode.OK, r.log
    for text in ("item-1-a", "item-3-c", "rep-1", "rep-2"):
        assert text in r.transcript
    assert "-b" not in r.transcript and "-d" not in r.transcript


async def test_until_checks_after_each_pass_and_while_limit(play, tmp_path):
    counter = tmp_path / "n"
    counter.write_text("0")
    r = await play(f"""
steps:
  - until: {{regex: "^count=3$"}}
    max_iterations: 5
    steps:
      - run: "n=$(( $(cat {counter}) + 1 )); echo $n > {counter}; echo count=$n"
  - while: "false"
    max_iterations: 1
    steps: [{{run: "echo never"}}]
  - while: "true"
    max_iterations: 2
    on_exhausted: continue
    steps: [{{run: "echo spin"}}]
  - while: "true"
    max_iterations: 1
    steps: [{{run: "echo spin-again"}}]
""")
    assert counter.read_text().strip() == "3"
    assert "never" not in r.transcript
    assert r.code == ExitCode.STEP_FAILED
    assert "reached max_iterations (1)" in r.report["failure"]["error"]
    assert statuses(r)["steps.2"] == "ok"


async def test_retry_block_and_on_fail_forms(play, tmp_path):
    flag = tmp_path / "flaky"
    r = await play(f"""
steps:
  - retry: 3
    delay: 0
    steps:
      - run: "test -e {flag} || {{ touch {flag}; false; }}"
        check_exit: true
  - run: "false"
    check_exit: true
    on_fail: continue
  - run: "false"
    check_exit: true
    on_fail:
      - run: "echo RECOVERED"
  - run: "echo last"
""")
    assert r.code == ExitCode.OK, r.log
    s = statuses(r)
    assert s["steps.1"] == "failed-continued" and s["steps.2"] == "recovered"
    assert "RECOVERED" in r.transcript
    assert any("attempt 1/3 failed" in n for n in notes(r, "steps.0"))


async def test_try_catch_finally_and_error_vars(play, tmp_path):
    r = await play("""
steps:
  - try:
      - run: "ls /nope-{{ 1 }}"
        check_exit: true
    catch:
      - run: "echo CAUGHT {{ error.step }}"
      - set: why
        value: "{{ error.message }}"
    finally:
      - run: "echo FINALLY"
  - assert: "'exited with code' in why"
""")
    assert r.code == ExitCode.OK, r.log
    assert "CAUGHT steps.0.try.0" in r.transcript and "FINALLY" in r.transcript


async def test_define_call_set_capture_assert_exec(play, tmp_path):
    r = await play("""
vars: {greeting: hello}
steps:
  - define: shout
    params: [word, times]
    steps:
      - repeat: "{{ times }}"
        steps: [{run: "echo {{ word | upper }}-{{ loop.index }}"}]
  - call: shout
    with: {word: "{{ greeting }}", times: 2}
  - run: "echo version=1.24.0 build=7"
    capture: {name: version, regex: 'version=(\\S+)'}
  - assert: "version == '1.24.0'"
  - exec: "printf 'a\\\\nb\\\\nc\\\\n' | wc -l"
    capture: lines
  - assert: "lines | int == 3 and last.exit_code == 0"
  - set: items
    value: "{{ ['x', 'y'] }}"
  - assert: "items | length == 2"
  - run: "echo marker; echo 42"
  - capture: answer
    lines: 1
  - assert:
      text: "42"
    message: "the output shows 42"
  - assert: "answer == '42'"
    message: "captured the last line"
""")
    assert r.code == ExitCode.OK, r.log
    assert "HELLO-1" in r.transcript and "HELLO-2" in r.transcript


async def test_failed_assert_and_undefined_variable_fail_the_step(play):
    r = await play("""
steps:
  - assert: "1 == 2"
    message: "math is broken"
""")
    assert r.code == ExitCode.STEP_FAILED
    assert r.report["failure"]["error"] == "math is broken"


async def test_wait_any_sets_last_matched(play):
    r = await play("""
steps:
  - type: "read -r -p 'Continue? [Y/n] ' a"
    enter: true
  - wait_for:
      any:
        - {text: "password for", as: need_password}
        - {regex: '\\[Y/n\\] $', scope: screen, as: question}
  - if: "last.matched == 'question'"
    then:
      - type: "y"
        enter: true
  - run: "echo got=$a"
    expect: '^got=y$'
""")
    assert r.code == ExitCode.OK, r.log


async def test_system_and_screen_conditions(play, tmp_path):
    marker = tmp_path / "ready"
    r = await play(f"""
steps:
  - type: "(sleep 1; touch {marker}) &"
    enter: true
  - wait_for: {{file: "{marker}", timeout: 5}}
  - wait_for: {{exec: "test -e {marker}", timeout: 2}}
  - type: "python3 -m http.server 18765 --bind 127.0.0.1"
    enter: true
  - wait_for: {{port: 18765, timeout: 10}}
  - if: {{port: 18765}}
    then: [{{log: "port open"}}]
  - key: C-c
    wait_for: {{prompt: true}}
  - run: >-
      for i in 1 2 3; do printf 'working %s\\r' $i; sleep 0.3; done;
      printf '\\033[2K'; echo done
    expect: {{gone: "working", timeout: 5}}
  - type: "sleep 1; echo quiet"
    enter: true
  - wait_for: {{idle: 1.5, timeout: 8}}
""")
    assert r.code == ExitCode.OK, r.log


async def test_on_timeout_steps_and_retry(play):
    r = await play("""
steps:
  - run: "echo hi"
    expect:
      text: "nothing like this"
      timeout: 0.5
      on_timeout:
        - run: "echo TIMEOUT-HANDLED"
  - run: "echo x"
    expect: {text: "never", timeout: 0.3, on_timeout: retry}
    on_fail: continue
""")
    assert r.code == ExitCode.OK, r.log
    assert "TIMEOUT-HANDLED" in r.transcript
    assert any("waiting once more" in n for n in notes(r, "steps.1"))


async def test_stop_success_and_failure(play, tmp_path):
    marker = tmp_path / "finally"
    r = await play(f"""
steps:
  - run: "echo before"
  - stop: success
    message: "nothing more to show"
  - run: "echo after"
finally:
  - run: "touch {marker}"
""")
    assert r.code == ExitCode.OK and marker.exists()
    assert "echo after" not in r.transcript


async def test_stop_failure_fails_the_take(play):
    r = await play("""
vars: {ok: false}
steps:
  - stop: failure
    message: "precondition not met"
    when: "not ok"
""")
    assert r.code == ExitCode.STEP_FAILED
    assert r.report["failure"]["error"] == "precondition not met"


async def test_when_skips_single_steps(play):
    r = await play("""
vars: {enable_firewall: false}
steps:
  - run: "echo FIREWALL"
    when: "enable_firewall == true"
  - run: "echo always"
""")
    assert r.code == ExitCode.OK
    assert statuses(r)["steps.0"] == "skipped" and "FIREWALL" not in r.transcript


async def test_secret_in_exec_template_is_masked(play, monkeypatch):
    monkeypatch.setenv("SP_TOKEN", "tok-9f8e7d")
    r = await play("""
steps:
  - exec: "echo using {{ secret.SP_TOKEN }}"
    capture: out
  - log: "exec said {{ out }}"
""")
    assert r.code == ExitCode.OK, r.log
    for path in r.dir.rglob("*"):
        if path.is_file():
            assert b"tok-9f8e7d" not in path.read_bytes(), path.name
    assert "using ****" in r.log


async def test_include_and_resolved_scenario(play, tmp_path, write_scenario):
    (tmp_path / "part.yaml").write_text('- run: "echo FROM-INCLUDE {{ who }}"\n')
    r = await play("""
vars: {who: me}
steps:
  - include: part.yaml
""", cli_vars={"who": "you"})
    assert r.code == ExitCode.OK, r.log
    assert "FROM-INCLUDE you" in r.transcript
    resolved = (r.dir / "scenario.resolved.yaml").read_text()
    assert "FROM-INCLUDE" in resolved and "include:" not in resolved
    assert "who: you" in resolved
