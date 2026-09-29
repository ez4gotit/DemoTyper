# `define`

*Control block.* Declare a reusable block with parameters; `call` runs it. Defining runs nothing.

## Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `define` (main) | text | required | Name of the block. |
| `params` | list of text | - | Parameter names; `call` gives each a value with `with`. |
| `steps` | list of anything | required | The steps to run. |

Every step also takes the [common options](index.md#common-options). `when` is not allowed on blocks other than `break`, `continue` and `stop`.

## Examples

```yaml
- define: create_user
  params: [name]
  steps:
    - run: "sudo useradd -m {{ name }}"
```

```yaml
- define: show_service
  params: [unit]
  steps:
    - run: "systemctl status {{ unit }} --no-pager | head -n 3"
```

## Common mistakes

- Defining runs nothing; use `call`. Names must be unique across the scenario and its includes.
