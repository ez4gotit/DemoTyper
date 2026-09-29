# `continue`

*Control block.* Skip to the next pass of the innermost loop (`continue: true`).

## Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `continue` (main) | true | required | true. |

Every step also takes the [common options](index.md#common-options).

## Examples

```yaml
- for_each: [a, b, c]
  steps:
    - continue: true
      when: "item == 'b'"
    - run: "echo {{ item }}"
```

```yaml
- repeat: 5
  steps:
    - continue: true
      when: "loop.index0 in [1, 3]"
    - run: "echo pass {{ loop.index }}"
```

## Common mistakes

- `continue` skips only the rest of the current pass; the loop goes on.
