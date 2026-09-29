# `open_console`

*Action.* Open a declared console mid-take (one with `start: false`, or one closed earlier).

## Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `open_console` (main) | text | required | Name of a declared console. |

Every step also takes the [common options](index.md#common-options).

## Examples

```yaml
# consoles: [..., {name: extra, start: false}]
- open_console: extra
```

```yaml
- close_console: extra
- open_console: extra        # a fresh shell
```

## Common mistakes

- Only consoles declared under `consoles` can be opened; give them `start: false` to open them later.
