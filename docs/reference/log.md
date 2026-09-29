# `log`

*Action.* Write a line to the take log only.

## Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `log` (main) | text | required | Text for the take log. |
| `level` | `debug` / `info` / `warning` / `error` | `info` | Log level. |

Every step also takes the [common options](index.md#common-options).

## Examples

```yaml
- log: "starting the slow part"
```

```yaml
- log: "version is {{ version }}"
  level: warning
```

## Common mistakes

- Secrets are refused in log lines.
