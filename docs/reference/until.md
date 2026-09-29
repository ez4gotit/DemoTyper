# `until`

*Control block.* Repeat until the condition holds; it is checked after each pass, so the steps run at least once (the condition usually looks at their output).

## Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `max_iterations` | integer | required | Upper limit of passes, so a take can never hang (required). |
| `delay` | number | `0.0` | Seconds to wait between passes. |
| `on_exhausted` | `fail` / `continue` | `fail` | fail (default) or continue when the limit is reached. |
| `steps` | list of anything | required | The steps to run. |
| `until` (main) | text or mapping or true/false | required | Expression or condition, checked after each pass. |

Every step also takes the [common options](index.md#common-options). `when` is not allowed on blocks other than `break`, `continue` and `stop`.

## Examples

```yaml
- until: { regex: "HTTP/1.1 200" }
  max_iterations: 10
  delay: 3
  steps:
    - run: "curl -sI http://localhost"
```

```yaml
- until: "status == 'ready'"
  max_iterations: 20
  steps:
    - exec: "cat /tmp/status"
      capture: status
```

## Common mistakes

- The condition is checked after each pass and looks at the output of the steps just run.
