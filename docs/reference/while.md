# `while`

*Control block.* Repeat while the condition holds; it is checked before each pass.

## Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `max_iterations` | integer | required | Upper limit of passes, so a take can never hang (required). |
| `delay` | number | `0.0` | Seconds to wait between passes. |
| `on_exhausted` | `fail` / `continue` | `fail` | fail (default) or continue when the limit is reached. |
| `steps` | list of anything | required | The steps to run. |
| `while` (main) | text or mapping or true/false | required | Expression or condition, checked before each pass. |

Every step also takes the [common options](index.md#common-options). `when` is not allowed on blocks other than `break`, `continue` and `stop`.

## Examples

```yaml
- while: "count | int < 3"
  max_iterations: 10
  steps:
    - run: "ls | wc -l"
      capture: count
```

```yaml
- while: { exec: "pgrep -x apt" }
  max_iterations: 60
  delay: 5
  steps: [{ log: "apt is still running" }]
```

## Common mistakes

- `max_iterations` is required, so a take can never hang.
- `while` checks before each pass; use `until` to run the steps at least once.
