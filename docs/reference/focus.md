# `focus`

*Action.* Bring a console to the front and highlight it. `zoom: true` makes its pane fill the screen for readability; `zoom: false` restores the layout.

## Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `focus` (main) | text | required | Console name. |
| `zoom` | true/false | - | true: the pane fills the screen; false: back to the layout. |

Every step also takes the [common options](index.md#common-options).

## Examples

```yaml
- focus: logs
  zoom: true
- pause: 3
- focus: logs
  zoom: false
```

```yaml
- focus: server              # highlight without typing
```

## Common mistakes

- Zoom only has an effect in split layouts.
