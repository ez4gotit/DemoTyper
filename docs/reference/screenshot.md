# `screenshot`

*Action.* Save a PNG of the screen into the take's screenshots/ folder.

## Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `screenshot` (main) | text or true | `true` | File name, or true for a name based on the step. |

Every step also takes the [common options](index.md#common-options).

## Examples

```yaml
- screenshot: after-install.png
```

```yaml
- screenshot: true           # named after the step
```

## Common mistakes

- Without a display (`--headless`), the console text is saved instead of a PNG.
