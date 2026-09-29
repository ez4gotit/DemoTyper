# `secret`

*Action.* Type a secret (a password) by name. Shown on screen as the program shows it (a password prompt shows nothing); masked as **** in every output. The step first waits until the terminal reads input without echo, so a secret is never typed where it would be visible. `hidden: false` drops that check.

## Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `wait_for` | mapping or text | - | After the input, wait for this condition instead of the default. |
| `expect` | mapping or text | - | Same as wait_for; a plain string is a regex. |
| `typing` | mapping | - | Typing speed and realism for this step (see defaults.typing). |
| `typos` | true/false or `on` / `off` | - | off turns auto-typos off for this step (on cannot force them where they are switched off). |
| `secret` (main) | text | required | Name of the secret (from --secrets or the environment). |
| `enter` | true/false | `false` | Press Enter after typing. |
| `hidden` | true/false | `true` | Wait until the terminal hides input (a password prompt) before typing. |

Every step also takes the [common options](index.md#common-options).

## Examples

```yaml
- type: "mysql -u root -p"
  enter: true
- secret: DB_ROOT_PASSWORD
  enter: true
  wait_for: { text: "mysql>" }
```

```yaml
- type: "ssh-add ~/.ssh/lab"
  enter: true
- secret: KEY_PASSPHRASE
  enter: true
```

## Common mistakes

- `secret` takes the secret's name, never the value. Give the value with `--secrets FILE` or an environment variable.
- The step waits until the terminal reads hidden input. If the program echoes, nothing is typed and the step fails. Only drop that check with `hidden: false` if you're sure.
- For sudo, an answer rule in `defaults.answers` is usually simpler than a `secret` step.
