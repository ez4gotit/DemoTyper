# `include`

*Control block.* Insert the steps of another file here (a list of steps, or a file with only `steps:`). The path is relative to the including file. Resolved when loading.

## Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `include` (main) | text | required | Path of the file to include, relative to this file. |

Every step also takes the [common options](index.md#common-options). `when` is not allowed on blocks other than `break`, `continue` and `stop`.

## Examples

```yaml
- include: common/login.yaml
```

```yaml
- include: ../shared/install-docker.yaml
```

## Common mistakes

- The path is relative to the file that contains the `include`.
- An included file holds a list of steps, or a mapping with only `steps:`.
