# `repeat`

*Control block.* Repeat the steps a fixed number of times.

## Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `repeat` (main) | integer or text | required | Number of passes. |
| `steps` | list of anything | required | The steps to run. |

Every step also takes the [common options](index.md#common-options). `when` is not allowed on blocks other than `break`, `continue` and `stop`.

## Examples

```yaml
- repeat: 3
  steps:
    - run: "curl -s localhost > /dev/null && echo ok {{ loop.index }}"
```

```yaml
- repeat: "{{ attempts }}"
  steps: [{ run: "make test" }]
```

## Common mistakes

- `loop.index` starts at 1; `loop.index0` starts at 0.
