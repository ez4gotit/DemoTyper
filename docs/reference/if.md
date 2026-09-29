# `if`

*Control block.* Run `then` if the condition holds; otherwise the first `elif` that holds, or `else`. The condition is an expression or a screen/system condition checked once.

## Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `if` (main) | text or mapping or true/false | required | Expression or condition, checked once. |
| `then` | list of anything | required | Steps to run when the condition holds. |
| `elif` | list of mapping | - | More branches: a list of {if, then}. |
| `else` | list of anything | - | Steps to run when no condition holds. |

Every step also takes the [common options](index.md#common-options). `when` is not allowed on blocks other than `break`, `continue` and `stop`.

## Examples

```yaml
- if: "env_name == 'prod'"
  then:
    - run: "echo production"
  else:
    - run: "echo test"
```

```yaml
- if: { exec: "systemctl is-active nginx" }
  then:
    - caption: "nginx is already running"
  else:
    - run: "sudo systemctl start nginx"
```

## Common mistakes

- `if` always needs `then`. To make one step conditional, use `when` on that step.
- `elif` is a list of `{if, then}` entries.
