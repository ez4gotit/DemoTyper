# `clear`

*Action.* Clear the console: `clear: command` (or `true`) types `clear`, `clear: key` sends Ctrl+L.

## Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `wait_for` | mapping or text | - | After the input, wait for this condition instead of the default. |
| `expect` | mapping or text | - | Same as wait_for; a plain string is a regex. |
| `typing` | mapping | - | Typing speed and realism for this step (see defaults.typing). |
| `typos` | true/false or `on` / `off` | - | off turns auto-typos off for this step (on cannot force them where they are switched off). |
| `clear` (main) | `command` / `key` or true | `command` | command (type `clear`) or key (Ctrl+L). |

Every step also takes the [common options](index.md#common-options).

## Examples

```yaml
- clear: command             # types `clear`
```

```yaml
- clear: key                 # Ctrl+L, nothing typed
```

## Common mistakes

- `clear` inside a full-screen program (vim, less) does not do what you expect; quit it first.
