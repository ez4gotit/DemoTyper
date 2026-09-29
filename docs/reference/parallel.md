# `parallel`

*Control block.* Run branches at the same time, one console per branch (spec 9.3). `wait: all` (default) ends when every branch is done; `wait: any` ends when the first branch is done and stops the others. A failing branch stops the others and fails the block.

## Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `parallel` (main) | list of mapping | required | Branches: a list of {console, steps}. |
| `wait` | `all` / `any` | `all` | all: end when every branch is done; any: end when the first is done and stop the others. |

Every step also takes the [common options](index.md#common-options). `when` is not allowed on blocks other than `break`, `continue` and `stop`.

## Examples

```yaml
- parallel:
    - console: server
      steps:
        - type: "python3 -m http.server 8080"
          enter: true
          wait_for: { text: "Serving HTTP" }
    - console: logs
      steps:
        - type: "tail -f access.log"
          enter: true
          wait_for: { idle: 1 }
```

```yaml
- parallel:
    - console: a
      steps: [{ run: "sleep 30" }]
    - console: b
      steps: [{ run: "echo done" }]
  wait: any                  # stop the slow branch
```

## Common mistakes

- Each branch needs its own console, and steps inside a branch can't name another console.
