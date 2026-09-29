# Wait conditions

Used by `wait_for`, `expect`, and (checked once) by `if`, `while`, `until`, `assert` and `when`. See [choosing a wait](../waiting.md) for when to use which.

Every condition also takes:

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `timeout` | number | - | Seconds to wait before failing (default: defaults.timeout). |
| `interval` | number | - | Seconds between checks (default 0.2). |
| `scope` | `since_last_input` / `screen` | - | since_last_input (default): only output after the last input; screen: the whole visible screen. |
| `on_timeout` | `fail` / `continue` / `retry` or list of anything | - | fail (default), continue, retry (wait once more), or a list of steps to run. |
| `console` | text | - | Run in this console instead of the current one. |
| `as` | text | - | Name stored in last.matched when this branch of `any` matches. |

## `all`

Holds when every condition holds in the same poll.

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `all` (main) | list of anything | required |  |

```yaml
- wait_for:
    all:
      - { port: 80 }
      - { port: 443 }
```


## `any`

Holds as soon as one of the conditions holds. Each may name a `console`.

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `any` (main) | list of anything | required |  |

```yaml
- wait_for:
    any:
      - { text: "[Y/n]", as: question }
      - { prompt: true, as: done }
```


## `exec`

An out-of-view command succeeds (exit code 0). Nothing is typed on screen.

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `exec` (main) | text | required |  |

```yaml
- wait_for: { exec: "systemctl is-active nginx", timeout: 30 }
```

```yaml
- if: { exec: "id alice" }\n  then: [{ log: "alice exists" }]
```


## `file`

A file or directory exists on the target (checked out of view).

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `file` (main) | text | required |  |

```yaml
- wait_for: { file: /var/run/app.pid }
```

```yaml
- assert: { file: ~/.ssh/id_ed25519 }
```


## `gone`

This text is no longer visible (a progress bar or spinner ended). Like `text`, it looks at the output since the last input, so the typed command itself does not count; `scope: screen` looks at the whole screen.

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `gone` (main) | text | required |  |

```yaml
- wait_for: { gone: "Downloading", timeout: 600 }
```

```yaml
- wait_for: { gone: "%", timeout: 120 }
```


## `idle`

The screen has not changed for this many seconds (for programs without a prompt).

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `idle` (main) | number | required |  |

```yaml
- wait_for: { idle: 2 }
```

```yaml
- type: "tail -f app.log"
  enter: true
  wait_for: { idle: 1 }
```


## `port`

A TCP port accepts connections: `port: 80` (on the target) or `port: "db:5432"`.

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `port` (main) | integer or text | required |  |

```yaml
- wait_for: { port: 80, timeout: 30 }
```

```yaml
- wait_for: { port: "db:5432" }
```


## `prompt`

The console's prompt is back: the prompt regex matches the last non-empty line and, when the hidden shell hook is active, the shell has finished a command since the last input.

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `prompt` (main) | true | `true` |  |

```yaml
- wait_for: { prompt: true }
```

```yaml
- key: C-c
  wait_for: { prompt: true }
```


## `regex`

This regular expression matches the output (multi-line mode: ^ and $ match per line).

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `regex` (main) | text | required | Regular expression; the first group (or the whole match) is kept. |

```yaml
- wait_for: { regex: 'HTTP/1\.1 (200|301)' }
```

```yaml
- run: "ip -4 addr"
  expect: 'inet 10\.'
```


## `text`

This exact text appears in the output.

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `text` (main) | text | required |  |

```yaml
- wait_for: { text: "Active: active (running)" }
```

```yaml
- run: "make"\n  expect: { text: "Build finished" }
```
