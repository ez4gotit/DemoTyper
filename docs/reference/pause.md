# `pause`

*Action.* Wait a fixed number of seconds so the viewer can read (scaled by --speed).

## Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `pause` (main) | number | required | Seconds (scaled by --speed). |

Every step also takes the [common options](index.md#common-options).

## Examples

```yaml
- pause: 2                   # let the viewer read the output
```

```yaml
- pause: 0.5
```

## Common mistakes

- Don't use `pause` to wait for a command. Use `wait_for`, which ends as soon as the condition holds.
