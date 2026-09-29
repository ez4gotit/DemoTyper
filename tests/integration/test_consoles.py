"""Several consoles: layouts, switching, focus/zoom, open/close, parallel, remote (phase 3)."""

from __future__ import annotations

import pytest

from scenarioplay.console import session as session_mod
from scenarioplay.exitcodes import ExitCode

from .conftest import FAST

pytestmark = pytest.mark.integration


def transcript(r, name):
    return (r.dir / "transcript" / f"{name}.txt").read_text()


def step(r, path):
    return next(s for s in r.report["steps"] if s["path"] == path)


@pytest.fixture
def tmux_calls(monkeypatch):
    """Record the tmux commands the session sends (to check layout and switching)."""
    calls: list[tuple[str, ...]] = []
    original = session_mod.Tmux.__call__

    async def spy(self, *args, **kwargs):
        calls.append(args)
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(session_mod.Tmux, "__call__", spy)
    return calls


async def test_split_layout_titles_and_switching(play, tmux_calls):
    r = await play(FAST + """
layout: split-horizontal
consoles:
  - {name: server, title: "Server"}
  - {name: client, title: "Client", size: 40%}
steps:
  - run: "echo on-server"
    console: server
  - use: client
  - run: "echo on-client"
  - run: "echo server-again"
    console: server
""", fast=False)
    assert r.code == ExitCode.OK, r.log
    assert "on-server" in transcript(r, "server") and "server-again" in transcript(r, "server")
    assert "on-client" in transcript(r, "client") and "on-server" not in transcript(r, "client")
    assert any(c[:1] == ("split-window",) and "-h" in c for c in tmux_calls)
    assert ("select-layout",) == next(c[:1] for c in tmux_calls if c[0] == "select-layout")
    titles = [c[-1] for c in tmux_calls if c[:1] == ("set-option",) and "@sp_title" in c]
    assert titles == ["Server", "Client"]
    assert any(c[0] == "resize-pane" and "-x" in c for c in tmux_calls)
    selects = [c for c in tmux_calls if c[0] == "select-pane"]
    # Only on changes: server at the start, then client, then server again.
    assert [c[-1] for c in selects] == ["%0", "%1", "%0"]


async def test_tabs_switch_windows(play, tmux_calls):
    r = await play(FAST + """
layout: tabs
consoles: [{name: one}, {name: two}]
steps:
  - run: "echo first"
  - run: "echo second"
    console: two
""", fast=False)
    assert r.code == ExitCode.OK, r.log
    assert sum(1 for c in tmux_calls if c[0] == "new-window") == 1
    assert sum(1 for c in tmux_calls if c[0] == "select-window") >= 2


async def test_focus_zoom_open_close(play, tmux_calls):
    r = await play(FAST + """
layout: split-vertical
consoles:
  - {name: main}
  - {name: extra, start: false}
steps:
  - open_console: extra
  - run: "echo in-extra"
    console: extra
  - focus: extra
    zoom: true
  - focus: extra
    zoom: false
  - close_console: extra
  - run: "echo back-in-main"
  - run: "echo too-late"
    console: extra
""", fast=False)
    assert r.code == ExitCode.STEP_FAILED
    assert "console 'extra' is closed" in r.report["failure"]["error"]
    assert "in-extra" in transcript(r, "extra")  # kept although closed
    zooms = [c for c in tmux_calls if c[0] == "resize-pane" and "-Z" in c]
    assert len(zooms) == 2  # zoom in, zoom out
    assert any(c[0] == "kill-pane" for c in tmux_calls)


async def test_parallel_all_runs_branches_at_the_same_time(play):
    r = await play(FAST + """
layout: split-horizontal
consoles: [{name: a}, {name: b}]
steps:
  - parallel:
      - console: a
        steps:
          - for_each: [1, 2]
            as: i
            steps: [{run: "sleep 1; echo A{{ i }}"}]
      - console: b
        steps:
          - for_each: [x, y]
            as: i
            steps: [{run: "sleep 1; echo B{{ i }}"}]
  - run: "echo after"
""", fast=False)
    assert r.code == ExitCode.OK, r.log
    assert "A1" in transcript(r, "a") and "A2" in transcript(r, "a")
    assert "Bx" in transcript(r, "b") and "By" in transcript(r, "b")
    assert "Bx" not in transcript(r, "a")
    # Four one-second commands: about 2 s in parallel, over 4 s one after another.
    assert step(r, "steps.0")["duration"] < 3.8


async def test_parallel_any_stops_the_slow_branch(play):
    r = await play(FAST + """
layout: split-horizontal
consoles: [{name: server}, {name: client}]
steps:
  - parallel:
      - console: server
        steps: [{run: "sleep 30", timeout: 60}]
      - console: client
        steps: [{run: "echo quick"}]
    wait: any
""", fast=False)
    assert r.code == ExitCode.OK, r.log
    assert step(r, "steps.0")["duration"] < 10
    assert any("finished first" in n for n in step(r, "steps.0")["notes"])


async def test_parallel_failure_fails_the_block(play):
    r = await play(FAST + """
layout: split-horizontal
consoles: [{name: a}, {name: b}]
steps:
  - parallel:
      - console: a
        steps: [{run: "sleep 20", timeout: 60}]
      - console: b
        steps: [{run: "false", check_exit: true}]
""", fast=False)
    assert r.code == ExitCode.STEP_FAILED
    assert "exited with code 1" in r.report["failure"]["error"]
    assert step(r, "steps.0")["duration"] < 10


async def test_parallel_validation(load):
    parsed, problems = load("""
        consoles: [{name: a}, {name: b}]
        layout: grid
        steps:
          - parallel:
              - console: a
                steps: [{run: ls}]
              - console: a
                steps: [{run: ls, console: b}]
    """)
    assert parsed is None
    text = " | ".join(p.message for p in problems)
    assert "each branch needs its own console" in text
    assert "would race" in text


FAKE_SSH = """#!/bin/bash
# Stand-in for ssh: logs its arguments, then runs the remote command locally with a
# prompt that shows it is "remote".
echo "$@" >> "{log}"
tty=no; args=()
while [ $# -gt 0 ]; do
  case "$1" in
    -t) tty=yes; shift ;;
    -o|-i|-p) shift 2 ;;
    *) args+=("$1"); shift ;;
  esac
done
dest="${{args[0]}}"; cmd="${{args[@]:1}}"
if [ $tty = yes ]; then
  export SHELL="{shell}"
fi
exec bash -c "$cmd"
"""

FAKE_SHELL = """#!/bin/bash
export PS1='remote:\\w$ '
exec bash --norc --noprofile -i
"""


async def test_remote_console_over_ssh(play, tmp_path):
    log = tmp_path / "ssh.log"
    shell = tmp_path / "fakeshell"
    shell.write_text(FAKE_SHELL)
    shell.chmod(0o755)
    ssh = tmp_path / "fakessh"
    ssh.write_text(FAKE_SSH.format(log=log, shell=shell))
    ssh.chmod(0o755)
    remote_dir = tmp_path / "remote-home"
    remote_dir.mkdir()
    r = await play(FAST + f"""
layout: split-horizontal
consoles:
  - {{name: local}}
  - name: box
    host: 192.0.2.10
    cwd: "{remote_dir}"
    ssh: {{user: student, key: ~/.ssh/lab, port: 2222, program: "{ssh}"}}
steps:
  - run: "pwd"
    console: box
    expect: "remote-home"
  - exec: "echo out-of-view > marker"
    console: box
  - wait_for: {{file: "{remote_dir}/marker", console: box, timeout: 5}}
""", fast=False)
    assert r.code == ExitCode.OK, r.log
    assert "remote:" in transcript(r, "box")
    calls = log.read_text().splitlines()
    assert any("-t" in c and "student@192.0.2.10" in c and "-p 2222" in c for c in calls)
    assert any("BatchMode=yes" in c and "out-of-view" in c for c in calls)
    assert (remote_dir / "marker").read_text() == "out-of-view\n"


async def test_check_exit_rejected_on_remote_console(load):
    parsed, problems = load("""
        consoles: [{name: main}, {name: box, host: lab2}]
        layout: tabs
        steps:
          - run: "false"
            console: box
            check_exit: true
    """)
    assert parsed is None and "cannot be installed on another machine" in problems[0].message
