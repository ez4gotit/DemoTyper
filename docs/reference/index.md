# Reference

One page per action and control block, generated from the code (options, types, defaults) and `docs/reference.yaml` (examples, mistakes).

## Actions

- [`assert`](assert.md): Fail if the condition is false: an expression, or a screen/system condition.
- [`caption`](caption.md): Show a subtitle line for some seconds without starting a chapter.
- [`capture`](capture.md): Store output in a variable.
- [`chapter`](chapter.md): Start a chapter: video chapter marker, subtitle and log section.
- [`clear`](clear.md): Clear the console: `clear: command` (or `true`) types `clear`, `clear: key` sends Ctrl+L.
- [`close_console`](close_console.md): Close a console mid-take; its text still goes into the transcript.
- [`enter`](enter.md): Press Enter (`enter: true`, or `enter: 3` to press it three times).
- [`exec`](exec.md): Run a command out of view (not typed on screen), e.g.
- [`focus`](focus.md): Bring a console to the front and highlight it.
- [`key`](key.md): Send a key or combination: C-c, C-d, C-l, Tab, Up, Down, Escape, F1-F12, M-x.
- [`log`](log.md): Write a line to the take log only.
- [`open_console`](open_console.md): Open a declared console mid-take (one with `start: false`, or one closed earlier).
- [`pause`](pause.md): Wait a fixed number of seconds so the viewer can read (scaled by --speed).
- [`record`](record.md): Control the video at any point.
- [`run`](run.md): Type a command, press Enter and wait for the prompt (or for `expect` / `wait_for`).
- [`screenshot`](screenshot.md): Save a PNG of the screen into the take's screenshots/ folder.
- [`secret`](secret.md): Type a secret (a password) by name.
- [`set`](set.md): Set or change a variable: `set: name` with `value:` (templates keep their type, so `value: "{{ packages }}"` stays a list).
- [`type`](type.md): Type text character by character.
- [`use`](use.md): Make a console the current one: later steps without `console:` run there.
- [`vm`](vm.md): VMware control mid-take (spec 4.4): `vm: snapshot`, `vm: revert` or `vm: reboot`.
- [`wait_for`](wait_for.md): Block until a screen condition holds (spec section 7).

## Control blocks

- [`break`](break.md): Leave the innermost loop (`break: true`, usually with `when`).
- [`call`](call.md): Run a `define`d block with parameter values from `with`.
- [`continue`](continue.md): Skip to the next pass of the innermost loop (`continue: true`).
- [`define`](define.md): Declare a reusable block with parameters; `call` runs it.
- [`for_each`](for_each.md): Repeat the steps for each item of a list (`for_each: [a, b]` or `"{{ var }}"`).
- [`if`](if.md): Run `then` if the condition holds; otherwise the first `elif` that holds, or `else`.
- [`include`](include.md): Insert the steps of another file here (a list of steps, or a file with only `steps:`).
- [`parallel`](parallel.md): Run branches at the same time, one console per branch (spec 9.3).
- [`repeat`](repeat.md): Repeat the steps a fixed number of times.
- [`retry`](retry.md): Run the steps; if one fails, wait `delay` seconds and run them all again, up to `retry` attempts in total.
- [`stop`](stop.md): End the take early: `stop: success` or `stop: failure`, with an optional message.
- [`try`](try.md): Run `try`; if a step fails, run `catch` (with {{ error.message }} and {{ error.step }}) instead of failing.
- [`until`](until.md): Repeat until the condition holds; it is checked after each pass, so the steps run at least once (the condition usually looks at their output).
- [`while`](while.md): Repeat while the condition holds; it is checked before each pass.

## Wait conditions

- [All conditions](conditions.md)

## Common options

Every step accepts these:

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `console` | text | - | Run in this console instead of the current one. |
| `timeout` | number | - | Seconds to wait before failing (default: defaults.timeout). |
| `on_fail` | `fail` / `continue` or mapping or list of anything | - | What to do when the step fails: fail, continue, {retry: N, delay: S}, or a list of recovery steps. |
| `when` | text or mapping or true/false | - | Run the step only if this expression or condition holds. |
| `label` | text | - | A name for --from/--to and the log. |

- `console`: run in this console instead of the current one.
- `timeout`: seconds for this step's wait (default `defaults.timeout`).
- `on_fail`: `fail` (default), `continue`, `{retry: N, delay: S}`, or a list of recovery steps.
- `when`: an expression or condition; the step is skipped when it is false.
- `label`: a name for `--from`/`--to` and the log.
