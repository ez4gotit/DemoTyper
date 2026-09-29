# `use`

*Action.* Make a console the current one: later steps without `console:` run there.

## Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `use` (main) | text | required | Console name. |

Every step also takes the [common options](index.md#common-options).

## Examples

```yaml
- use: client
- run: "curl -s localhost"
```

```yaml
- use: server
```

## Common mistakes

- `use` does not change the screen by itself; the console comes forward when it is typed into (or with `focus`).
