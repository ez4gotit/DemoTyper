# `stop`

*Control block.* End the take early: `stop: success` or `stop: failure`, with an optional message. `finally` still runs.

## Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `stop` (main) | `success` / `failure` | required | success or failure. |
| `message` | text | - | Text for the log and the report. |

Every step also takes the [common options](index.md#common-options).

## Examples

```yaml
- stop: success
  message: "nothing more to show"
```

```yaml
- stop: failure
  message: "the lab VM has no network"
  when: "not online"
```

## Common mistakes

- `finally` still runs after `stop`.
