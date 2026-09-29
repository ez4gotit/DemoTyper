# `wait_for`

*Action.* Block until a screen condition holds (spec section 7).

## Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `wait_for` (main) | mapping or text | required | The condition to wait for. |

Every step also takes the [common options](index.md#common-options).

## Examples

```yaml
- wait_for: { text: "Serving HTTP", console: server, timeout: 20 }
```

```yaml
- wait_for:
    any:
      - { text: "password for", as: need_password }
      - { prompt: true, as: done }
```

```yaml
- wait_for: { port: 8080, timeout: 30 }
```

## Common mistakes

- `text` and `regex` see only output since the last input. Use `scope: screen` to look at everything visible.
- `idle` never holds while something keeps changing on screen, such as a clock or `top`.
