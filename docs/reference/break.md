# `break`

*Control block.* Leave the innermost loop (`break: true`, usually with `when`).

## Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `break` (main) | true | required | true. |

Every step also takes the [common options](index.md#common-options).

## Examples

```yaml
- for_each: "{{ hosts }}"
  as: h
  steps:
    - exec: "ping -c1 -W1 {{ h }}"
    - break: true
      when: "last.exit_code == 0"
```

```yaml
- repeat: 10
  steps:
    - break: true
      when: "loop.index > 3"
```

## Common mistakes

- `break` and `continue` only work inside a loop.
