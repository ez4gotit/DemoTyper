# `close_console`

*Action.* Close a console mid-take; its text still goes into the transcript.

## Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `close_console` (main) | text | required | Name of an open console. |

Every step also takes the [common options](index.md#common-options).

## Examples

```yaml
- close_console: extra
```

```yaml
- close_console: logs
  when: "not keep_logs"
```

## Common mistakes

- The last open console cannot be closed.
