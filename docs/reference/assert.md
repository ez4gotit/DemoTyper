# `assert`

*Action.* Fail if the condition is false: an expression, or a screen/system condition.

## Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `assert` (main) | text or mapping or true/false | required | Expression or condition that must hold. |
| `message` | text | - | Text for the log and the report. |

Every step also takes the [common options](index.md#common-options).

## Examples

```yaml
- assert: "version matches '^1\\.2'"
  message: "nginx 1.2x is installed"
```

```yaml
- assert: { port: 80 }
  message: "the web server listens"
```

## Common mistakes

- Write a bare expression (`x == 1`), not `{{ x }} == 1`.
