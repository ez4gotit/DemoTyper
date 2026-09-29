# `type`

*Action.* Type text character by character. Press Enter only with `enter: true`. With `tab: true`, the text is typed as a *prefix* and then Tab is pressed so the shell autocompletes the rest (e.g. `type: "cat /etc/host"` + `tab: true` -> /etc/hostname). Pair it with `expect`/`wait_for` to confirm the completion; typos are off on the prefix so completion is not thrown off.

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
| `tab` | true/false | `false` | After typing, press Tab to autocomplete the rest. |

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

```yaml
- type: "cat /etc/host"      # type a prefix, then Tab-complete the rest
  tab: true
  expect: "hostname"
  enter: true
```

## Common mistakes

- Text with newlines is refused unless `enter_newlines: true`, so nothing is run by accident.
- A Tab inside the text would trigger completion; send it with `key: Tab`, or use `tab: true` to autocomplete a prefix.
- With `tab: true`, pair it with `expect`/`wait_for`: the completion is not typed, so add a check that it produced the intended command.
