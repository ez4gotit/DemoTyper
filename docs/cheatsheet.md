# Cheat sheet

```yaml
version: 1
meta: { title: "…" }
target:   { kind: local | vmware, vmx, snapshot, ssh: {host: auto, user, key, port},
            record: guest | host, boot_timeout: 180,
            terminal: {command, font, font_size},
            recorder: {backend: auto|x11grab|wf-recorder, display, fps, crf, lead_in, tail,
                       autostart: true} }
defaults: { typing: {profile: novice|normal|expert|robot, speed: 0.7, cps, word_pause,
                     reword: {chance, hesitation}, typos: {rate, seed}},
            screenshots: {chapters: none|start|end|both, text: false},
            prompt: '[$#%>] ?$', timeout: 60, after_command_pause: 1.0,
            on_fail: fail|continue|{retry: N}, answers: [{when: regex, secret|text}] }
layout: single | split-horizontal | split-vertical | grid | tabs
consoles: [{name, title, shell: bash|zsh|sh, cwd, prompt, env, host, ssh, size, start}]
vars: { name: value }
setup: [ … ]      # not recorded
steps: [ … ]
finally: [ … ]    # always runs, not recorded
```

## Input

```yaml
- run: "cmd"                     # type, Enter, wait for the prompt
  expect: 'regex'                # or wait_for: {…}
  check_exit: true
  capture: name                  # or {name, regex, group, lines}
- type: "text"                   # enter: true, enter_newlines: true, tab: true (autocomplete)
- paste: "text"                  # or {buffer: name}: insert instantly (pseudo-paste)
- enter: true                    # or a count
- key: C-c                       # Tab Up Down Escape F1-F12 M-x PageDown; repeat: N
- secret: NAME                   # into a hidden prompt; enter: true
- clear: command | key
```

## Waiting

```yaml
- wait_for: {prompt: true}
- wait_for: {text: "…"}  /  {regex: "…"}  /  {gone: "…"}  /  {idle: 2}
- wait_for: {exec: "cmd"}  /  {file: path}  /  {port: 80}
- wait_for: {any: [{text: …, as: a}, {prompt: true, as: b}]}     # → last.matched
  # options: timeout, interval, scope: screen, on_timeout: fail|continue|retry|[steps],
  #          console
```

## Showing

```yaml
- chapter: "Task 1: …"          # caption: "…"
- caption: "…"                  # duration: 4
- pause: 2
- screenshot: name.png           # or {file, console: logs, text: true}
- record: pause | resume          # cut time out of the current video
- record: stop | start            # separate video files; start takes clip: name
- log: "…"                      # level: info
```

## Data

```yaml
- set: name
  value: "{{ expr }}"
- capture: name                  # regex, group, lines, from: output|screen|last_output
- assert: "expr"                 # or a condition; message: "…"
- exec: "cmd"                    # out of view; capture: name, check_exit
```

`{{ var | join(' ') | upper | lower | trim | default('x') | length | int }}`
Built-ins: `env.X`, `secret.X`, `take.id`, `last.exit_code`, `last.output`, `last.matched`,
`loop.index`, `loop.item`, `error.message`.
Expressions: `== != < <= > >= and or not in matches ( )`.

## Blocks

```yaml
- if: "expr" | {condition}       # then: [...], elif: [{if, then}], else: [...]
- for_each: "{{ list }}"         # as: item, steps
- repeat: 3                      # steps
- while: "expr"                  # max_iterations (required), delay, on_exhausted, steps
- until: {condition}             # checked after each pass
- retry: 3                       # delay, on_exhausted, steps
- try: [...]                     # catch: [...], finally: [...]
- define: name                   # params: [...], steps
- call: name                     # with: {…}
- break: true / continue: true / stop: success|failure   # with `when`
- include: path.yaml
- parallel: [{console, steps}]   # wait: all | any
```

Every step: `console`, `timeout`, `on_fail`, `when`, `label`.

## Consoles and VMs

```yaml
- use: client
- focus: logs                    # zoom: true/false
- open_console: name / close_console: name
- vm: snapshot|revert|reboot     # name: snapshot
```

## Commands

```bash
scenarioplay validate FILE [--var k=v] [--vars f.yaml]
scenarioplay run FILE [--dry-run] [--no-record] [--headless] [--speed 2] [--step]
                      [--from NAME] [--to NAME] [--var k=v] [--vars f.yaml]
                      [--secrets f.yaml] [--typos 0.05 | --no-typos] [--burn-subtitles]
                      [--cast] [--target local|vmware] [--out DIR] [--keep-session] [-v]
scenarioplay doctor [--target vmware --vmx PATH --key PATH]
scenarioplay schema > schema/scenarioplay.schema.json
```

Exit codes: 0 success, 1 validation error, 2 step failure, 3 environment error,
130 interrupted.
