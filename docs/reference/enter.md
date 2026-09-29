# `enter`

*Action.* Press Enter (`enter: true`, or `enter: 3` to press it three times).

## Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `wait_for` | mapping or text | - | After the input, wait for this condition instead of the default. |
| `expect` | mapping or text | - | Same as wait_for; a plain string is a regex. |
| `enter` (main) | true/false or integer | `true` | true, or how many times to press Enter. |

Every step also takes the [common options](index.md#common-options).

## Examples

```yaml
- enter: true
```

```yaml
- enter: 2                   # press Enter twice
  wait_for: { text: "Done" }
```

## Common mistakes

- On a `type` step, `enter: true` is an option of that step, not a separate step.
