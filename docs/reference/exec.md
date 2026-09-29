# `exec`

*Action.* Run a command out of view (not typed on screen), e.g. for checks. Sets {{ last.exit_code }} and {{ last.output }}; `capture: name` stores its output.

## Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `exec` (main) | text | required | Shell command, run out of view. |
| `capture` | text | - |  |
| `check_exit` | true/false | `false` | Fail the step when the command exits with a non-zero code. |
| `cwd` | text | - | Directory to run in. |

Every step also takes the [common options](index.md#common-options).

## Examples

```yaml
- exec: "systemctl is-active nginx"
  capture: state
- assert: "state == 'active'"
```

```yaml
- exec: "rm -rf /tmp/lab && mkdir /tmp/lab"
  check_exit: true
```

## Common mistakes

- Nothing appears on screen: `exec` is for checks and preparation, not for what the viewer should see.
- On a console with `host:`, `exec` runs on that machine.
