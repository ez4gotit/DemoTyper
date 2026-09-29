# `call`

*Control block.* Run a `define`d block with parameter values from `with`.

## Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `call` (main) | text | required | Name of a defined block. |
| `with` | mapping | - | Values for the block's parameters. |

Every step also takes the [common options](index.md#common-options). `when` is not allowed on blocks other than `break`, `continue` and `stop`.

## Examples

```yaml
- call: create_user
  with: { name: alice }
```

```yaml
- for_each: [alice, bob]
  as: who
  steps:
    - call: create_user
      with: { name: "{{ who }}" }
```

## Common mistakes

- Every parameter in `params` needs a value in `with`.
