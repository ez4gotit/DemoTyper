# ScenarioPlay: Implementation Plan

Based on *Technical Specification: Scenario Typing Runner (ScenarioPlay)*, Sep 29, 2026 (updated revision: adds §4.4, the top-level key table in §5, `when`, and the block syntax rule in §8).
Section numbers such as §6.2 point to the spec.

---

## 1. Key technical decisions

| Area | Decision | Why |
| --- | --- | --- |
| Runtime | Python 3.10+, **asyncio** throughout | `parallel` branches, typing timers, polling waits and "Ctrl+C stops typing at once" are all simpler with cancellable tasks than with threads. |
| CLI | `click`, a single `scenarioplay` entry point in `pyproject.toml` (hatchling), installed with `pipx` | Matches §11 and §13. Exit codes 0/1/2/3/130 go through one `ExitCode` enum. |
| YAML | `ruamel.yaml` (round-trip loader) | Every node keeps its line and column, which §11 needs for line-numbered errors. PyYAML drops them. |
| Model and schema | **pydantic v2** models per action/block. `scenarioplay schema` is generated from them, and a copy is checked in at `schema/scenarioplay.schema.json` | One source of truth for validation and editor autocompletion. A CI test fails if the checked-in schema is out of date. |
| Expressions and templates | **Own small Pratt parser** (§5.2) that serves both `if`/`while` expressions and `{{ … \| filter }}` interpolation | Jinja2 can't express `matches`, and a sandboxed Jinja2 is still more power than we want. About 300 lines, fully unit-tested, gives clear error positions. |
| SSH | **asyncssh** | asyncio-native and works on a Windows host. Windows OpenSSH has no ControlMaster, so calling the `ssh` binary for every keystroke would be too slow. One connection per target, one exec channel per command. |
| tmux control | `tmux -L scenarioplay-<take> …` argv calls through a `Transport` (local subprocess or SSH exec) | A private server socket means we never touch the user's own tmux. One process call per character is about 2–5 ms locally and a single RTT over SSH, well under the ~110 ms gap between keystrokes at 9 cps. |
| Recording format | Record to **MKV** (or fragmented MP4), then remux to `video.mp4` with `-c copy` | A crash or kill still leaves a playable file, as the "failed take always leaves a video" rule requires. Stop ffmpeg with `q` on stdin, never SIGKILL. |
| Wiki | MkDocs Material in `docs/` | Markdown in the repo that also publishes as a static site (§14.3). |
| Dev and CI | Development in **WSL2** (tmux, Xvfb or WSLg). CI on GitHub Actions `ubuntu-latest` with tmux, Xvfb and ffmpeg | The dev machine runs Windows. Every Linux-side piece still needs a real tmux to test against. |

---

## 2. Repository layout

```
scenarioplay/
├─ pyproject.toml
├─ src/scenarioplay/
│  ├─ cli.py                  # click commands: validate, run, doctor, schema
│  ├─ exitcodes.py
│  ├─ loader/
│  │  ├─ yaml_io.py           # ruamel load, node → (file, line, col) map
│  │  ├─ includes.py          # include resolution, cycle detection
│  │  ├─ model.py             # pydantic models: Scenario, Target, Defaults, Console…
│  │  ├─ steps.py             # step dispatch: which action/block key is present
│  │  ├─ validate.py          # semantic checks (vars, consoles, labels, secrets in captions…)
│  │  └─ schema.py            # JSON Schema export, built from the registries
│  ├─ lang/
│  │  ├─ lexer.py, parser.py  # expression language (§5.2)
│  │  ├─ evaluator.py         # safe evaluation, no Python eval
│  │  ├─ template.py          # {{ }} rendering, filters; single-expression strings return native values
│  │  └─ scope.py             # variable scopes, env.*, secret.*, loop.*, last.*, take.*
│  ├─ engine/
│  │  ├─ engine.py            # walks the step tree, on_fail/timeout wrapper, --from/--to, --step
│  │  ├─ context.py           # RunContext: scope, current console, clock, reporter, target
│  │  ├─ blocks.py            # if, for_each, repeat, while/until, retry, try, parallel, define/call
│  │  ├─ signals.py           # Break, Continue, Stop, StepFailed exceptions
│  │  └─ plan.py              # --dry-run plan printer
│  ├─ actions/                # plugins, one class each (§13 extensibility)
│  │  ├─ base.py, registry.py # @action("run") decorator + entry-point group
│  │  ├─ typing_actions.py    # run, type, enter, key, secret, clear
│  │  ├─ flow_meta.py         # pause, chapter, caption, log, screenshot, record
│  │  ├─ vars.py              # set, capture, assert
│  │  ├─ exec.py, console.py  # exec; focus, use, open_console, close_console
│  │  └─ vm.py
│  ├─ conditions/             # wait_for plugins: prompt, text, regex, gone, idle, any/all, exec, file, port
│  ├─ typing/
│  │  ├─ profiles.py          # novice/normal/expert/robot, parameter merge
│  │  ├─ planner.py           # pure function: text + params + rng → keystroke events
│  │  ├─ typos.py             # the 5 typo kinds, budget, protect list
│  │  ├─ layouts/us.yaml, de.yaml, ru.yaml   # adjacency, base + shift layer
│  │  └─ verifier.py          # read input line before Enter, repair
│  ├─ console/
│  │  ├─ tmux.py              # thin async wrapper over tmux commands
│  │  ├─ driver.py            # Console objects: send_char, send_key, capture, markers
│  │  ├─ screen.py            # capture scopes (since_last_input / screen), wrapped-line join
│  │  ├─ layout.py            # single/split/grid/tabs, pane titles, active highlight
│  │  └─ hooks/bash_rc.sh, zsh/.zshrc   # hidden PROMPT_COMMAND / precmd hook
│  ├─ transport/local.py, ssh.py        # run(argv) → (rc, stdout, stderr); read/write file
│  ├─ target/local.py, vmware.py, vmrun.py
│  ├─ recorder/
│  │  ├─ base.py, timeline.py # wall clock ↔ video time, pause segments
│  │  ├─ ffmpeg_x11.py, wf_recorder.py, portal.py, host_capture.py
│  ├─ report/
│  │  ├─ masker.py            # every output goes through it
│  │  ├─ takelog.py, srt.py, chapters.py, report_json.py, transcript.py
│  └─ doctor.py
├─ schema/scenarioplay.schema.json
├─ docs/                      # syntax wiki (§14.3)
├─ examples/                  # 4 scenarios (§14.4) + a sample lab PDF
└─ tests/unit, tests/integration, tests/fixtures
```

---

## 3. Core mechanisms

### 3.1 Console driver (tmux)

- **Session:** `tmux -L sp-<take> new-session -d -x W -y H` with `history-limit 100000`, `status` on for pane titles, and `pane-border-status top` so the active pane's colour and title show (§9.2). Layouts are built with `split-window`, `select-layout` and `new-window` (for tabs).
- **Visible window:** the target runs a full-screen terminal attached to that session. The command is configurable; the defaults are `xterm -fa <font> -fs <size> -fullscreen` or `alacritty`, which are easy to set up the same way every time. In VMware mode this is launched over SSH with `DISPLAY=:0` and `XAUTHORITY` taken from the logged-in desktop user.
- **Typing one character:** `send-keys -t <pane> -l -- <ch>`. Gotchas:
  - `;` as a single argv item is tmux's command separator, so send it as `\;`.
  - Over SSH, each argv item goes through `shlex.quote`.
  - The tmux server needs a UTF-8 locale for non-ASCII input. `doctor` checks this.
  - A literal Tab or newline in `type` text is refused by the validator. Use `key: Tab` or `enter_newlines: true` instead.
- **Keys:** `send-keys -t <pane> C-c` (no `-l`), mapped from the §6 key names.
- **Scheduling:** each keystroke runs against a monotonic deadline (`next = prev + delay`). Transport latency is absorbed, not added on top, and `--speed` divides every delay.

### 3.2 Screen reading and waits

- **Capture:** `capture-pane -p -J -S <start> -E -` (`-J` joins wrapped lines so regexes work on long lines).
- **`since_last_input` scope:** just before the first keystroke of a step, the runner stores an absolute line marker `history_size + cursor_y` from `display -p`. Later captures start at that marker. Setting `history-limit` high keeps the marker stable during a take. If `history_size` ever shrinks, or the pane is on the alternate screen (`#{alternate_on}`, as with vim or less), the wait falls back to `screen` scope and logs a warning.
- **Poll loop:** each condition implements `async check(ctx) -> Match | None`, and one generic loop handles `interval`, `timeout` and `on_timeout`. `idle` hashes the capture and waits for N seconds without a change. `exec`, `file` and `port` run out of view through the transport (`test -e`, `bash -c '</dev/tcp/127.0.0.1/80'` or `ss`).
- **CPU budget (§13):** one capture-pane call per active wait every 0.2 s, and only for the consoles being waited on. The integration suite measures guest CPU use.

### 3.3 Hidden shell hook: exit codes and command completion

Each console shell is started as `bash --rcfile <sp_rc>`, or zsh with `ZDOTDIR=<sp_dir>`. That rc file sources the user's normal rc, then adds a hook that runs first in `PROMPT_COMMAND` (bash) or `precmd` (zsh). The hook writes this line to `/tmp/scenarioplay/<take>/<console>.status`:

```
<seq> <exit_code> <last command line from history>
```

Nothing is ever typed on screen for this. The hook gives three things:

1. **`last.exit_code`** for `check_exit` (§7.4).
2. **A reliable "command finished" signal:** `seq` goes up. The `prompt` condition is met when `seq` has gone up **and** the prompt regex matches the last non-empty line. This avoids the race where the prompt regex matches before the shell has even read the Enter.
3. **Proof that no command ran with a typo:** the executed command line is compared with the intended text after every `run`. This makes the "50 takes, no typo executed" criterion measurable, and every mismatch is logged as an error.

Consoles on another machine (`host:` in §9.1) have no hook. There, `prompt` uses the regex alone, and the validator rejects `check_exit` on them.

### 3.4 Typing planner and typos (§6.1–6.3)

- `planner.plan(text, params, rng) -> list[Event]`. An event is `Char(c, delay)`, `Backspace(delay)` or `Pause(s)`. It is a **pure function**, so it can be tested with Hypothesis. The key property: replaying the events into a buffer always gives exactly `text`.
- Typo kinds follow the spec's table. Neighbours come from the layout YAML, including the shift layer, so `!` can be mistyped as `@`. A character that isn't in the configured layout gets no neighbour typo.
- Budget rules: `max_per_line`, `min_length`, `protect`. The rng is `Random(seed ^ hash(step_path))`, so each step's typos stay the same across takes even if steps are added elsewhere.
- **Verifier before Enter:** it reads the text from the input-start position (stored before typing) to the cursor. It stops at the cursor so zsh-autosuggestion ghost text is ignored. If the text doesn't match the intent, it backspaces to the common prefix and retypes, then tries `C-u` and a clean retype, then fails the step. Every typo and repair goes to `take.log` with position, intended character and typed character.
- **Typo gate (§6.2):** before planning a step's keystrokes, the driver makes one check, `typos_allowed(console)`. It returns true only if all of these hold:
  - the step is not `secret` or `key`, and the step doesn't set `typos: off`;
  - `#{alternate_on}` is 0, so no full-screen program such as nano, vim or less is open;
  - the prompt regex matches the last non-empty line;
  - the input start position was recorded, so the verifier can read the line back.

  Otherwise the planner runs with typos disabled and the log records `typos auto-off: <reason>`. A step's `typos: on` can't override the gate. The engine applies the gate itself, so no action plugin can skip it.

### 3.5 Expression and template language

- Grammar: literals, names with dots (`loop.index`, `last.matched`), indexing, `== != < <= > >=`, `and or not`, `in`, `matches`, parentheses, and filters `| name(args)` in templates.
- A string that is exactly one `{{ expr }}` returns the **native** value, so `for_each: "{{ packages }}"` gets a list. Mixed strings render as text.
- Undefined names are errors. `validate` checks them statically against declared vars, `--var`, `capture`/`set` targets, loop `as` names and `define` params.
- **Secrets:** `secret.X` values are registered with the `Masker` when they are resolved. Every sink (log, srt, report, transcript, `scenario.resolved.yaml`) writes through the masker. The validator rejects `secret.*` in `caption`, `chapter` and `log` (§12).

### 3.6 Engine

- **Step dispatch:** each step mapping must contain exactly one registered action or block keyword. The keyword's value is the main argument, following the §8 rule (`if: <cond>`, `repeat: 3`, `retry: 3`, `define: name`). All other keys are that keyword's fields plus the common options. `setup`, `steps`, `finally` and nested step lists all use the same dispatcher.
- **Checks for `when` and `if`:** the validator rejects `if` without `then`, and `when` on any block other than `break`, `continue` and `stop` (§8.2). The top level accepts exactly the 10 keys in §5.
- **Conditions:** one `Condition` type serves `when`, `if`, `while`, `until`, `wait_for` and `expect`. A string is parsed as an expression; a mapping is parsed as a screen or system condition (§7.1). `wait_for` polls a condition until its timeout. Block conditions and `when` call the same `check()` once (§8).
- The loader returns a tree of typed nodes. The engine calls `await node.execute(ctx)` on each one inside a generic wrapper that handles `when`, `label`, `timeout`, `on_fail` (`fail`, `continue`, `retry: N` or recovery steps), timing and logging.
- Control flow uses exceptions (`BreakLoop`, `ContinueLoop`, `StopTake`, `StepFailed`). Scenario-level `finally` always runs, including after `stop` and Ctrl+C.
- `parallel` is an `asyncio.TaskGroup` with one console per branch. The validator checks that branches don't share a console. `wait: any` cancels the other branches.
- Every loop needs `max_iterations`, and the schema enforces it.
- **Take order:**
  1. Prepare the target (revert to `target.snapshot` if set).
  2. Create the consoles and open the terminal window.
  3. Run `setup`, not recorded.
  4. Start the recorder, then the lead-in.
  5. Run `steps`.
  6. Tail, then stop the recorder.
  7. Run `finally`.
  8. Write the outputs.

  `finally` runs after any failure, `stop` or Ctrl+C. By default `finally` is not recorded, since `setup` isn't either (see §6, item 7).
- `--from/--to` resolves labels and chapter titles to tree paths. `setup` always runs. Steps outside the range are skipped and logged as skipped.
- `--step` pauses before each leaf step, reading Enter from the runner's own stdin (not the recorded terminal).
- `--dry-run` walks the same tree with a `PlanContext`. Loops over static lists expand; runtime-dependent branches print as `? if <expr>`.

### 3.7 Recorder and timeline

- `Recorder.start()` waits until ffmpeg reports its first frame (`-progress pipe:` gives `frame=`). That moment is video t=0 on the monotonic clock.
- `Timeline` maps runner time to video time. Chapter and caption stamps go through it, which is how the 0.5 s accuracy requirement is met.
- `record: pause/resume` ends the current segment and starts a new one. The paused gap is subtracted in `Timeline`. At the end the segments are concatenated, and a caption notes the skipped time.
- A watchdog task checks that the recorder process is alive. If it dies, the take fails immediately (§10.1).
- Backends:
  - `ffmpeg -f x11grab` for X11 (phase 1).
  - `wf-recorder` for wlroots compositors.
  - The xdg-desktop-portal ScreenCast API plus PipeWire for GNOME and KDE on Wayland. It needs a first-run permission and a stored `restore_token`.
  - Host capture for VMware mode B (`gdigrab` of the Workstation window on Windows, `x11grab` of the window on a Linux host).
  - All backends are phase 4 except x11grab.

### 3.8 Targets

- **`local`:** a `LocalTransport`, used directly.
- **`vmware`:**
  1. `vmrun -T ws revertToSnapshot <vmx> <snap>`.
  2. `vmrun start <vmx> gui|nogui`: `gui` for mode B, `nogui` for mode A.
  3. `getGuestIPAddress -wait`, which needs open-vm-tools in the guest.
  4. Wait until SSH answers.
  5. Wait until a graphical session exists (poll for the user's Xorg process and a readable `DISPLAY`).
  6. Open an `SSHTransport`.

  `vmrun` is found through PATH, the default install locations on Windows and Linux, or a `--vmrun` option.
- **Mid-take `vm` (§4.4):**
  - **Validator:** with `record: guest`, `vm snapshot`, `vm revert` and `vm reboot` are rejected anywhere in `steps` (including includes and `define` bodies reached from `steps`). The error gives the line number and the fix, `target.record: host`. They are always allowed in `setup`. They are rejected on the `local` target.
  - **Runtime:**
    1. Mark every console as lost.
    2. Run the `vm` command.
    3. Call `getGuestIPAddress -wait`, then poll SSH until it answers. Steps 3 and 4 share one `target.boot_timeout` deadline (default 180 s).
    4. Wait for the desktop session.
    5. Rebuild the tmux session, layout, consoles (including `host:` consoles), hook and terminal window.
    6. Restore the current console and zoom state, then resume with the next step.

    The host recorder keeps running throughout, and the log records the gap as a `vm` phase.
  - **Stale state:** `since_last_input` markers and hook `seq` values are reset. Variables are kept. A wait still running on the old session fails with a clear "console lost" error.

---

## 4. Phased work plan

The effort figures are rough, for one developer who knows the stack, and include tests.

### Phase 1: Core, local (about 3 weeks)

| # | Work package | Done when |
| --- | --- | --- |
| 1.1 | Repo skeleton, pyproject, click CLI, exit codes, CI (lint, mypy, pytest), WSL2 dev notes | `pipx install .` works and CI is green |
| 1.2 | ruamel loader with line map; pydantic models for all 10 top-level keys (unknown keys rejected) and phase-1 actions; "one keyword per step" dispatch; `validate` with line-numbered errors; `schema` export | 5 seeded-error fixtures each report the right line |
| 1.3 | Transport (local) and tmux wrapper on a private socket; single-console session; full-screen terminal launch | Integration test types into a real tmux and reads it back |
| 1.4 | Shell hook (bash first, then zsh); status file reader | `seq` and exit code are read correctly after `true`/`false` |
| 1.5 | Typing planner (basic speed parameters: cps, jitter, word/punctuation pause, think_before, profiles), no typos yet; `--speed` | Property tests pass; typed output matches the input, including `\| ~ $ { } \ ; ' "` and Cyrillic |
| 1.6 | Actions: `run`, `type`, `enter`, `key`, `pause`, `chapter`; conditions: `prompt`, `text`, `regex`; `expect` | Example scenario runs with `--no-record` |
| 1.7 | ffmpeg x11grab recorder, Timeline, MKV→MP4 remux, watchdog, lead-in and tail | Recording under Xvfb in CI produces a playable file of the expected length |
| 1.8 | Reporter: take folder, `take.log`, `chapters.txt`, `subtitles.srt`, `report.json`, transcripts, screenshot on failure; fail-fast; Ctrl+C handling | Killing a take mid-run still leaves video, log and screenshot |
| **Demo** | 10-command nginx install scenario on Ubuntu (X11) | Acceptance criteria for phase 1 (§15) |

### Phase 2: Control flow and data (about 3 weeks)

| # | Work package |
| --- | --- |
| 2.1 | Expression parser and evaluator, template renderer and filters, scope chain, `--var`, `--vars`, `env.*`, built-ins |
| 2.2 | Secrets: sources (`--secrets` file, env), Masker wired into every sink, validator rule, `secret` action |
| 2.3 | Shared `Condition` type (expression or checked-once screen/system condition); `when` on actions and on `break`/`continue`/`stop`; blocks `if/elif/else`, `for_each` (`as` default `item`), `repeat`, `while/until` + `max_iterations` + `on_exhausted`, `break/continue`, `stop` |
| 2.4 | `retry: N` block, `try/catch/finally`, per-step `on_fail`, `defaults.on_fail`, `setup` (unrecorded) and `finally` |
| 2.5 | `include` (relative paths, cycle detection, line map across files), `define/call` with params |
| 2.6 | `set`, `capture` (regex group, lines, from), `assert`, `exec` (out of view), `check_exit`, conditions `any/all` with `as`, `gone`, `idle`, `exec`, `file`, `port`, `on_timeout` variants |
| 2.7 | Static checks in `validate`: undefined vars, unknown consoles, duplicate labels, missing `max_iterations`, secrets in captions, `if` without `then`, `when` on blocks, `parallel` branches that share a console, `vm` in `steps` with `record: guest` |
| **Demo** | Loops-and-conditions example, run under 2 variable sets. A grep over the take folder finds no secret value. |

### Phase 3: Multi-console (about 2 weeks)

| # | Work package |
| --- | --- |
| 3.1 | Consoles list with per-console prompt, cwd, env and status file; `use`; `console:` on every step |
| 3.2 | Layouts: single, split-horizontal/vertical, grid, tabs; `size`; pane titles; active-pane highlight; tab switching before typing |
| 3.3 | `focus` + `zoom` (`resize-pane -Z`), `open_console`, `close_console` |
| 3.4 | `parallel` with `wait: all/any`, cancellation, per-branch logging |
| 3.5 | Remote consoles (`host:`): ssh started inside the pane, prompt by regex only, validator restrictions |
| **Demo** | Server, client and logs consoles with `tail -f`, `parallel` and `curl`, checked for readability at the target resolution and font size |

### Phase 4: VMware and polish (about 4 weeks)

| # | Work package |
| --- | --- |
| 4.1 | `vmrun` wrapper (Windows and Linux hosts), `vmware` target, asyncssh transport, readiness waits with `boot_timeout`, `vm` action with rebuild and resume after a revert or reboot (§4.4) |
| 4.2 | Recording mode B (host capture), Wayland backends (wf-recorder, portal) |
| 4.3 | Full typing realism: all 5 typo kinds, layouts us/de/ru plus custom YAML, notice delay, hesitation, backspace speed, burst, shifted slowdown, verifier, `--typos` and `--no-typos` |
| 4.4 | `doctor`, `--dry-run`, `--step`, `--from/--to`, `--keep-session`, `--burn-subtitles`, optional asciinema `.cast` |
| 4.5 | Wiki (all 8 sections of §14.3), 4 example scenarios, guest and host setup guides |
| 4.6 | Reliability runs: 10 consecutive takes from a snapshot; typo soak test (50 takes × 50 commands with the hook comparing executed commands) |
| **Demo** | Same scenario, 10 takes in a row from snapshot. A new author writes a working scenario from a PDF using only the wiki. |

Note: the verifier and the typo gate (3.4) are small and protect correctness. I suggest building them with the planner in phase 1, even though typos come in phase 4.

---

## 5. Testing strategy

| Layer | What | How |
| --- | --- | --- |
| Unit | Parser and evaluator, templates, filters, masker, step dispatch, schema, Timeline, SRT and chapter formatting | pytest; snapshot tests for error messages with line numbers |
| Property | Typing planner and typo engine | Hypothesis: replaying the events gives the text; budget and protect rules hold; the same seed gives the same events |
| Integration | Driver, hook, waits, blocks, layouts, parallel | Real tmux on a private `-L` socket, bash and zsh, run in CI |
| Fault injection | Verifier | A driver wrapper that drops, duplicates or corrupts characters at random. Checks that the executed command (from the hook) always equals the intended text. |
| Recording | x11grab, remux, pause segments, timestamp accuracy | Xvfb in CI. The scenario prints a visible timestamp at each chapter; OCR or frame checks confirm it is within 0.5 s. |
| System (manual or nightly) | VMware target, Wayland, mode B | Self-hosted runner with VMware Workstation, before phase 4 acceptance |

---

## 6. Spec gaps and inconsistencies to resolve

### 6.1 Resolved by the updated spec

| Earlier gap | Resolution in the spec | Where the plan uses it |
| --- | --- | --- |
| Top-level keys ("five" vs. seven or more) | §5 table: exactly 10 keys; anything else is an error | 3.6, WP 1.2 |
| `if` as both a guard and a block | `when` guards a single step; `if` is always a block with `then` (§6, §8.2) | 3.6, WP 2.3, 2.7 |
| Shape of loop conditions (`condition:` vs. inline) | §8 rule: the keyword's value is the main argument; there are no `condition`, `in` or `times` fields | 3.6 dispatch |
| Typos where the input can't be read back | §6.2: typos switch off automatically, and `typos: on` can't override that | 3.4 typo gate |
| `vm` mid-take with guest recording | §4.4: rejected by the validator (snapshot too); allowed in `setup`; rebuild after the guest is back, with `boot_timeout` | 3.8, WP 4.1 |

### 6.2 Decided (proposals accepted on 2026-09-29)

All proposals below were accepted as written and are what the code implements.

1. **Is `until` checked before or after its steps?** It isn't stated. The §8.1 `curl` example only works if the condition is checked **after** each pass, because on the first check no `curl` has run yet. **Proposal:** `while` checks before each pass. `until` checks after each pass, so its steps always run at least once.
2. **`wait_for` and `expect` as options on input actions.** §7.3, §8.1 (`parallel`) and §9.3 put `wait_for:` on `run` and `type`, but the §6 table doesn't list it. **Proposal:** any input action may carry `wait_for` or `expect`, and it replaces that action's default wait. The two are aliases, and a step may set only one of them.
3. **Which output a checked-once screen condition sees.** §8 says it is checked once, without waiting, but not whether that is the output since the last input or the whole screen. **Proposal:** the default is the current console's `since_last_input`, and it can be changed with `scope:` inside the condition.
4. **`console` inside a condition.** §9.3 writes `wait_for: { text: …, console: logs }`, putting `console` inside the condition instead of on the step. **Proposal:** allow both. A `console` inside a condition wins, which lets `any`/`all` watch several consoles at once.
5. **Actions used but missing from the §6 table.** These are `record: pause/resume` (§10.1), `use`, `open_console` and `close_console` (§9.2). **Proposal:** add them to the table as regular actions.
6. **Bare secret names.** §7.3 writes `secret: SUDO_PASS`, a bare name, while §5.1 uses `{{ secret.NAME }}`. **Proposal:** the `secret` action takes a bare name; everywhere else uses the template form.
7. **Is `finally` recorded?** `setup` is explicitly not recorded; `finally` isn't specified. **Proposal:** not recorded by default, since it is usually cleanup. `finally` could be recorded if it had its own `record: true` flag.
8. **`check_exit` and `exec` on remote `host:` consoles.** The hidden hook can't be installed there without typing. **Proposal:** the validator rejects `check_exit` on them, and `exec` runs on the main target unless it has a `host:` option.
9. **Which consoles are rebuilt after a revert.** §4.4 says "every declared console". **Proposal:** rebuild the consoles that were open at that moment, including any opened with `open_console` and excluding any closed with `close_console`.
10. **What `--speed` scales.** **Proposal:** typing delays, `pause`, `think_before` and hesitation. Wait timeouts, `boot_timeout`, lead-in and tail are not scaled.
11. **The "same sequence of steps" requirement in §13.** With `seed: null` typos differ between takes. **Proposal:** "same sequence" means the same steps, branches and loop indices. Keystroke-level identity only applies when a `seed` is set.

### 6.3 Decisions made while building phase 1

1. **Keywords that are also options.** `enter` (an option of `type`), `caption` (of `chapter`) and `wait_for` (of input steps) are also actions. When a step contains several keywords, the "pure" action wins, then `enter` and `caption`, then `wait_for`. So `{type: y, enter: true}` is a `type` step, `{enter: true, wait_for: …}` is an `enter` step, and `{wait_for: …}` alone is a `wait_for` step. Two pure actions in one step are an error.
2. **Extra configuration keys** under existing top-level keys:
   - `target.terminal`: `{command, font, font_size}`;
   - `target.recorder`: `{backend, display, fps, crf, codec, preset, lead_in, tail, draw_mouse}`;
   - `defaults.interval`;
   - `defaults.clear_after_setup` (default true), which clears the screen and scrollback after `setup` so the video starts clean.
3. **`setup` and `finally` are typed at `robot` speed**, since they aren't recorded.
4. **Default prompt regex** is `[$#%>] ?$`, tested against the last line both with and without trailing spaces.
5. **`expect: "<string>"`** is a regex. `expect:` also accepts a full condition mapping, as an alias of `wait_for`.
6. **Chapters for YouTube:** a first chapter within 5 s of the start is written as `00:00:00`. A later first chapter gets an "Intro" line before it. `report.json` keeps the exact times.
8. **Automatic answers (an addition to the spec).** `defaults.answers` and `consoles[].answers` are lists of `{when: regex, secret: NAME | text: "…", enter: true}`.
   - **When they fire:** during every wait, a rule is checked against the text before the cursor. Each prompt line is answered once.
   - **Secret answers:** a secret is typed only while the terminal reads hidden input, meaning termios shows `icanon` and `-echo`, read with `stty -F <pane tty>`. A shell prompt also has echo off but shows `-icanon`, so it never qualifies. If the same secret is asked for again within one wait, the step fails, so a wrong sudo password never gets three attempts on camera.
   - **The `secret` step** applies the same hidden-input check before typing.

   Secrets are read from `--secrets FILE` first, then from the environment. They are resolved before the take starts (a missing one gives exit 3) and are masked in every output. This brings the `secret` part of WP 2.2 forward from phase 2.
9. **Protection against running a mistyped command** works in two layers. Before Enter, the command line is read back and compared with the intended text, then repaired or the step fails. After the prompt returns, the hook's record of the executed command is compared again. Any mismatch goes into `report.json` → `executed_mismatches`, which must stay empty.

---

## 6.4 Phase 1 status

Implemented: every work package in phase 1 (1.1–1.8), plus the verifier and typo gate brought forward from 3.4.

- **Tests at the end of phase 1:** 83 in total, including 14 for secrets and answers. All 83 pass in WSL Ubuntu 24.04 (tmux 3.4, bash, zsh, xterm) under Xvfb. CI runs the same setup.
- **Recorded take, verified on video:** `examples/hello-shell.yaml` recorded under Xvfb at 1920×1080. The frames show the typed commands, colored prompts, symbols and Cyrillic.
  - *Timing:* a step's recorded video time matches the first changed frame to within 33 ms (one frame; the spec allows 0.5 s). The first chapter falls at 2.017 s for a 2 s lead-in.
  - *Window size:* under bare Xvfb the xterm window isn't full screen, because `-fullscreen` needs a window manager. The take log now records the window size in cells.
- **WSLg:** its `:0` is XWayland, whose root window x11grab captures as black. `doctor` and the take log warn about this, and the recorded-take test checks the last frame for terminal text.
- **Timing fix:** ffmpeg's progress reports lag capture by about 1.6 s (x264 buffering). The runtime estimate of the first frame now uses the first progress report, which lands within 0.05 s of the true time. The exact time is still read from the file at the end.
- **Not yet run:** the nginx acceptance demo (`examples/nginx-install.yaml`) on an Ubuntu desktop with real sudo.

---

## 6.5 Phase 2 status

Implemented: WP 2.1–2.7. That covers the expression language and templates (their own parser, no Python eval), variables with `--var`/`--vars`, and the built-ins. It also covers the blocks (`if/elif/else`, `for_each`, `repeat`, `while`, `until`, `retry`, `try/catch/finally`, `define/call`, `break/continue/stop`, `include`), `when`, the `on_fail` policies, and `set/capture/assert/exec`. The rest is `last.*`, the new conditions (`gone`, `idle`, `exec`, `file`, `port`, `any/all`), `on_timeout`, and the static checks.

- **Acceptance:** `examples/loops-and-conditions.yaml` runs with its own `vars` (dev: the `else` branch) and with `--vars examples/vars/prod.yaml` (prod: the `then` branch, 4 services, 3 replicas). No output file contains the deploy token (`tests/integration/test_acceptance_phase2.py`).
- **Tests:** 141 in total, all passing in WSL under Xvfb.

Decisions made while building phase 2:

1. **Conditions are expressions; everything else is text.** `when`, `if`, `while`, `until` and `assert` take bare expressions (`mode == 'prod'`). Writing `{{ }}` there is a validation error with a hint. Text anywhere else is a template.
2. **Types of rendered values.** A string that is exactly `{{ expr }}` keeps the value's type (lists, numbers). Inside longer text: `true`/`false`, null as empty, lists space-joined.
3. **Priority of variable sources follows spec 5.1 literally:** file `vars` < `--var` < `--vars` file < run-time values. `set` updates the innermost loop or call variable of that name, otherwise the global run-time layer, so values set inside a loop remain after it.
4. **Undefined variables.** Names neither declared in `vars` nor assigned by `set`/`capture` are a warning in a plain `validate`, and an error in `run` or in `validate --var ...`.
5. **`gone` reads the output since the last input**, like `text` and `regex`. Otherwise the typed command line, which often contains the watched text, would keep it "visible" forever. `scope: screen` gives the whole screen.
6. **`capture` from `output`, and `last.output`**, cover the text from the Enter up to the returned prompt, without the prompt line.
7. **`on_timeout: retry`** waits once more with the same timeout. For re-running the whole step, use `on_fail: {retry: N}`.
8. **Secrets in templates** are allowed where nothing is typed or shown (`exec`, `set`, `assert`, conditions). They are rejected in `run`/`type` text, which would appear on screen and in shell history, and in captions, chapters and logs. Referenced secrets are loaded before the take starts.
9. **`include`** accepts a file holding a list of steps, or a mapping with only `steps:`. Paths are relative to the including file, cycles are detected, and errors report the included file's own line numbers. `scenario.resolved.yaml` inlines includes and records the starting variable values.

---

## 6.6 Phase 3 status

Implemented: WP 3.1–3.5.

- **Consoles:** each has its own prompt, cwd, environment, hook and answer rules. `console:` works on every step, and `use` changes the current console.
- **Layouts:**
  - `split-horizontal`, `split-vertical` and `grid` place panes in one window, in the order declared. `size` works in the two split layouts.
  - `tabs` gives one window per console, with a tab bar.
  - Panes show titles on their borders, and the console being typed into is highlighted.
- **Console actions:** `focus`, including zoom, plus `open_console` and `close_console`.
- **`parallel`** supports `wait: all` and `wait: any`, stops the other branches when one fails, and gives each branch its own variables and `last.*`.
- **Remote consoles (`host:`):** ssh runs inside the pane. Out-of-view `exec` and the system conditions run on that machine.

**Acceptance:** `examples/multi-console.yaml` (server, client and logs in a grid, started with `parallel`) runs end to end (`tests/integration/test_acceptance_phase3.py`). It was also recorded under Xvfb at 1920×1080, with frames checked:
- the two branches type at the same moment;
- the pane titles are readable and the active one is highlighted;
- long commands wrap cleanly;
- the zoomed access log shows all three requests.

**Tests:** 151, all passing under Xvfb.

Decisions made while building phase 3:

1. **Split direction follows tmux's naming.** `split-horizontal` puts panes side by side, `split-vertical` stacks them, and `grid` is tmux's `tiled`. Panes keep their YAML order because each new pane splits the previous one.
2. **`single` with several consoles** shows one console at a time, switching to the one being typed into (a warning suggests `tabs` or a split layout).
3. **Consoles are declared up front.** `start: false` declares a console that `open_console` opens later, so the validator knows every console name. A closed console's text still goes into its transcript. Using a closed console fails the step with a clear message.
4. **Input activates its console:** typing, Enter and keys first select the pane or window, with a short pause so viewers can follow. Waits don't switch consoles. In `parallel` branches, split-layout panes aren't switched, so two consoles can be typed into at once.
5. **Per-branch state uses asyncio context variables:** current console, step record, variable scope (loop variables) and `last.*`. Global variables are shared.
6. **Remote consoles:**
   - The pane runs `ssh -t` with `StrictHostKeyChecking=accept-new`, then `cd <cwd>; exec $SHELL -l` on the remote side.
   - Out-of-view commands use `ssh -o BatchMode=yes`.
   - There's no hook there: the prompt is found by the regex alone, `check_exit` is rejected, and `ssh.program` can be overridden (the tests use a stand-in).
7. **The black-screen check runs in the background**, because a full-frame grab on a cold start took about 3 s and was stretching the lead-in.
8. **Window size under bare Xvfb:** without a window manager the terminal can't go full screen, and a fixed xterm geometry wider than the screen silently cuts off the right edge. On a desktop the window manager's full-screen mode avoids this. The take log records the window size in cells.

---

## 6.7 Phase 4 status

**Tests:** 180 in total. All pass in WSL, 179 under Xvfb; the VMware end-to-end test needs a real X socket, so it runs outside Xvfb. Lint is clean, and the schema and generated docs are checked to be current.

| WP | State | Verified how |
| --- | --- | --- |
| 4.1 VMware target | Done, except running against a real Linux guest. Includes: `vmrun` wrapper (found on Windows and Linux); asyncssh transport; revert, start, IP, SSH and desktop waits within `boot_timeout`; the terminal and x11grab recorder in the guest (mode A); `vm: snapshot/revert/reboot` with console rebuild and transcripts kept across the reboot; the §4.4 validator rules; `--target`. | In-process SSH server plus a stand-in `vmrun`: a full take with `vm: reboot` over real SSH. On this Windows host, `doctor --target vmware` ran the real `vmrun` (list, listSnapshots) read-only. No Linux guest exists here, so no take has run in a real VM. |
| 4.2 Host recording and Wayland | Mode B (`gdigrab` of the Workstation window on Windows, `x11grab` on Linux) and wf-recorder (wlroots) are done. The GNOME/KDE ScreenCast portal is **not done**; the docs recommend an Xorg session. | Mode B: the command line is tested, and `doctor` confirmed ffmpeg's `gdigrab` on this host. wf-recorder: a stand-in that behaves like it (SIGINT finishes the file, segments). Neither has recorded real video here. |
| 4.3 Typing realism | Done: all five typo kinds; us/de/ru and custom YAML layouts with the Shift layer; notice delay, hesitation, backspace speed, budget, `protect`, `seed`; the typo gate (shell prompt plus Enter in the same step); every typo logged; `--typos`/`--no-typos`. | Hypothesis: every plan replays to the exact text. Soak in real bash and zsh: 80 commands at a 12 % typo rate, zero executed mismatches, all outputs correct. |
| 4.4 CLI and outputs | Done: `doctor` (local and vmware host), `--dry-run` (block tree), `--step`, `--from/--to`, `--keep-session`, `--burn-subtitles`, `--cast`, `record: pause/resume` (segments joined, skipped time captioned, chapter times corrected), `soak`. | Integration tests; pause/resume and burned subtitles on real recordings under Xvfb. |
| 4.5 Wiki, examples, setup guides | Done: all 8 wiki sections (MkDocs); reference pages generated from the code with 2+ examples and common mistakes per keyword (each example is validated); 6 examples (single-console, multi-console, loops/conditions, VMware with snapshot reset, lab3 from the PDF walkthrough, hello); setup guide for the guest and the host. | `test_docs.py`: pages are current, every keyword has examples, every example validates. |
| 4.6 Reliability | `scenarioplay soak FILE --takes 10` runs N takes and fails unless all succeed and follow the same step sequence (branches and loop passes compared; typos and timing ignored). Soak test: 3 takes of the loops example, identical. | The "10 takes from a snapshot" and "50 takes × 50 commands" runs need the lab VM, or `SP_SOAK_TAKES=50 SP_SOAK_COMMANDS=50` locally (about 45 min). |

**Still to do for phase 4 acceptance (§15):**
- Run `examples/vmware-lab.yaml` or `lab3.yaml` 10 times with `soak` against a real Ubuntu guest with a `clean` snapshot.
- Have a new author write a scenario from a PDF using only the wiki.
- Optionally, the ScreenCast portal backend for GNOME and KDE on Wayland.

Decisions made while building phase 4:

1. **Typos only where they are checked:** on a shell prompt and in a step that presses Enter (the verifier runs before that Enter). `type` without Enter at the prompt never gets typos.
2. **`repeat` is both a block and an option of `key`**, so it uses the same "also an option" priority as `enter`, `caption` and `capture`.
3. **The recorder runs through the transport:** ffmpeg in the guest over SSH (mode A), with segments and screenshots fetched over SFTP. The black-screen check uses ffmpeg's `signalstats` so it works remotely.
4. **Transcripts across `vm: revert/reboot`:** each console's text is captured before the guest restarts and joined with a `--- vm reboot ---` line.
5. **`scenarioplay soak`** defines "same sequence of steps" as step paths, statuses, branches and loop passes. Typo lines and timings vary between takes and are ignored.

---

## 7. Proposed answers to the spec's open questions

| Question | Recommendation |
| --- | --- |
| GUI automation later? | Not in this plan. Keep the Driver interface narrow so an X11 input driver (xdotool) could be added as a plugin later. |
| X11 or Wayland, which distro? | **Ubuntu 24.04 with an Xorg session** as the reference guest. x11grab is the simplest and most reliable backend, and Wayland comes in phase 4. |
| VMware host OS | **Windows 11** (this machine), with Linux supported. Hence asyncssh and Windows-friendly `vmrun` discovery. |
| Default recording mode | **Mode A (inside the guest).** It gives native resolution, no window-occlusion problems, and exact timestamps. Mode B is only needed for `vm revert` mid-take. |
| Resolution and font | 1920×1080 at 30 fps; terminal font 18–20 px monospace (for example JetBrains Mono), about 100×30 cells per full pane. Confirm with a sample video before phase 3. |
| Multi-language subtitles | Not needed at first. `caption` and `chapter` could later take `{en: …, ru: …}` and write one `.srt` per language. |

---

## 8. Main risks

| Risk | Mitigation |
| --- | --- |
| Launching the full-screen terminal from SSH into the guest's desktop (DISPLAY, XAUTHORITY, auto-login) | Guest setup guide covers auto-login and xhost/XAUTHORITY; `doctor` checks it |
| Wayland portal needs user consent | Phase 4; store a restore token; X11 stays the default |
| Chapter timestamp drift | Frame-0 calibration plus the CI accuracy test (§5) |
| Prompt regex fragility (colours, multi-line prompts, zsh themes) | Detection uses the hook's `seq`, with the regex only as a second check; the wiki lists regexes for common shells |
| SSH latency on the per-character path | Deadline scheduling absorbs it; a latency check in `doctor` warns above 30 ms |
| Scope creep in the scenario language | Plugins for actions and conditions; the schema is generated from the registries so the language grows without engine changes |
