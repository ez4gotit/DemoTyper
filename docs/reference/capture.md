# `capture`

*Action.* Store output in a variable. `from`: `output` (since the last input, default), `screen` (visible screen) or `last_output` (output of the last `run`).

## Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `capture` (main) | text | required | Variable name. |
| `regex` | text | - | Regular expression; the first group (or the whole match) is kept. |
| `group` | integer or text | - | Which regex group to keep (number or name). |
| `lines` | integer | - | Keep only the last N lines. |
| `from` | `output` / `screen` / `last_output` | `output` | output (since the last input), screen, or last_output (of the last run). |

Every step also takes the [common options](index.md#common-options).

## Examples

```yaml
- run: "df -h /"
- capture: used
  regex: '(\d+)%'
```

```yaml
- capture: last_line
  lines: 1
  from: last_output
```

## Common mistakes

- Captured values are text. Compare them as numbers with `| int`, as in `used | int > 80`.
- Without a regex group, the whole match is kept.
