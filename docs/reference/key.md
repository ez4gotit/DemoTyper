# `key`

*Action.* Send a key or combination: C-c, C-d, C-l, Tab, Up, Down, Escape, F1-F12, M-x...

## Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `wait_for` | mapping or text | - | After the input, wait for this condition instead of the default. |
| `expect` | mapping or text | - | Same as wait_for; a plain string is a regex. |
| `key` (main) | text | required | Key name: C-c, M-x, Tab, Up, Escape, F5, PageDown, ... |
| `repeat` | integer | `1` | Press the key this many times. |

Every step also takes the [common options](index.md#common-options).

## Examples

```yaml
- key: C-c
  wait_for: { prompt: true }
```

```yaml
- key: Up                    # previous command from history
  repeat: 2
- key: Enter
```

## Common mistakes

- Names follow tmux: `C-c` (Ctrl+C), `M-x` (Alt+X), `PageDown`, `F5`. `Ctrl+C` is not a valid name.
