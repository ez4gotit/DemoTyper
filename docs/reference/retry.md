# `retry`

*Control block.* Run the steps; if one fails, wait `delay` seconds and run them all again, up to `retry` attempts in total.

## Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `retry` (main) | integer | required | Number of attempts in total. |
| `delay` | number | `1.0` | Seconds to wait between passes. |
| `on_exhausted` | `fail` / `continue` | `fail` | fail (default) or continue when the limit is reached. |
| `steps` | list of anything | required | The steps to run. |

Every step also takes the [common options](index.md#common-options). `when` is not allowed on blocks other than `break`, `continue` and `stop`.

## Examples

```yaml
- retry: 3
  delay: 5
  steps:
    - run: "wget https://example.com/file.tar.gz"
      check_exit: true
```

```yaml
- retry: 2
  on_exhausted: continue
  steps: [{ run: "ping -c1 -W1 10.0.0.1", check_exit: true }]
```

## Common mistakes

- `retry: 3` means three attempts in total.
- For one step, `on_fail: {retry: 2}` is shorter.
