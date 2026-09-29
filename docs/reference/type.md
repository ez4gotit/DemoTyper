# `type`

*Action.* Type text character by character. Press Enter only with `enter: true`.

## Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `wait_for` | mapping or text | - | After the input, wait for this condition instead of the default. |
| `expect` | mapping or text | - | Same as wait_for; a plain string is a regex. |
| `typing` | mapping | - | Typing speed and realism for this step (see defaults.typing). |
| `typos` | true/false or `on` / `off` | - | off turns auto-typos off for this step (on cannot force them where they are switched off). |
| `type` (main) | text | required | The text to type. |
| `enter` | true/false | `false` | Press Enter after typing. |
| `enter_newlines` | true/false | `false` | Press Enter for each newline in the text. Without this, text with newlines is refused. |

Every step also takes the [common options](index.md#common-options).

## Examples

```yaml
- type: "tail -f /var/log/syslog"
  enter: true
  wait_for: { idle: 2 }
```

```yaml
- type: "ls /etc/ng"         # no Enter: show tab completion next
- key: Tab
```

```yaml
- type: "cat > notes.txt\nfirst line\nsecond line"
  enter_newlines: true
- key: C-d
```

## Common mistakes

- Text with newlines is refused unless `enter_newlines: true`, so nothing is run by accident.
- A Tab inside the text would trigger completion; send it with `key: Tab`.
