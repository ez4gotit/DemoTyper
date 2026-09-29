# `try`

*Control block.* Run `try`; if a step fails, run `catch` (with {{ error.message }} and {{ error.step }}) instead of failing. `finally` always runs.

## Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `try` (main) | list of anything | required | Steps that might fail. |
| `catch` | list of anything | - | Steps to run when a step in `try` fails; {{ error.message }} and {{ error.step }} are set. |
| `finally` | list of anything | - | Steps that always run afterwards. |

Every step also takes the [common options](index.md#common-options). `when` is not allowed on blocks other than `break`, `continue` and `stop`.

## Examples

```yaml
- try:
    - run: "sudo systemctl start app"
      check_exit: true
  catch:
    - log: "app did not start: {{ error.message }}"
  finally:
    - run: "sudo journalctl -u app -n 5 --no-pager"
```

```yaml
- try:
    - assert: { file: /etc/app.conf }
  catch:
    - run: "sudo cp app.conf /etc/"
```

## Common mistakes

- Without `catch` the failure still fails the take; `finally` runs either way.
