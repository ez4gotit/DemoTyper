# `run`

*Action.* Type a command, press Enter and wait for the prompt (or for `expect` / `wait_for`).

## Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `wait_for` | mapping or text | - | After the input, wait for this condition instead of the default. |
| `expect` | mapping or text | - | Same as wait_for; a plain string is a regex. |
| `typing` | mapping | - | Typing speed and realism for this step (see defaults.typing). |
| `typos` | true/false or `on` / `off` | - | off turns auto-typos off for this step (on cannot force them where they are switched off). |
| `run` (main) | text | required | The command to type; Enter is pressed and the prompt awaited. |
| `check_exit` | true/false | `false` | Fail the step when the command exits with a non-zero code. |
| `capture` | text or mapping | - | Store the command's output in a variable: a name, or {name, regex, group, lines}. Needs the prompt to come back. |

Every step also takes the [common options](index.md#common-options).

## Examples

```yaml
- run: "sudo apt-get update"
  timeout: 300
  check_exit: true
```

```yaml
- run: "sudo apt install nginx"
  expect: '\[Y/n\]'          # wait for the question instead of the prompt
- type: "y"
  enter: true
  wait_for: { prompt: true, timeout: 600 }
```

```yaml
- run: "nginx -v 2>&1"
  capture: { name: version, regex: 'nginx/(\S+)' }
```

## Common mistakes

- A command that never returns (`tail -f`, a server) makes `run` wait for the prompt until it times out. Use `type` with `enter: true` and a `wait_for` such as `{text: "Serving"}` or `{idle: 1}`.
- `expect` looks only at output produced after Enter. It never matches the typed command itself.
- `check_exit` needs the prompt to come back, so it can't be combined with `expect`.
