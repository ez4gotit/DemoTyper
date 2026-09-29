# `record`

*Action.* Pause or resume the video (spec 10.1), e.g. around a long download. On resume a caption says how much time was skipped; chapter times stay correct.

## Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `record` (main) | `pause` / `resume` | required | pause or resume. |
| `caption` | true/false | `true` | Subtitle text. |

Every step also takes the [common options](index.md#common-options).

## Examples

```yaml
- record: pause
- run: "sudo apt-get dist-upgrade -y"
  timeout: 1800
- record: resume             # adds a "(12 min 05 s skipped)" subtitle
```

```yaml
- record: pause
- run: "make -j8"
- record: resume
  caption: false
```

## Common mistakes

- Pausing twice, or resuming without pausing first, only logs a warning.
