# `screenshot`

*Action.* Save a PNG of the screen into the take's screenshots/ folder. It works while recording, while recording is stopped, and with --no-record. With `console` it crops to that console's pane; with `text` it also saves the console text (HTML with colours, and plain text). A headless take has no screen, so it saves the text only.

## Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `screenshot` (main) | text or true or mapping | `true` | File name, true (named after the step), or {file, console, text}. |
| `text` | true/false | - | Also save the console text as .html and .txt (default: defaults.screenshots.text). |

Every step also takes the [common options](index.md#common-options).

## Examples

```yaml
- screenshot: after-install.png
```

```yaml
- screenshot:                # only the `logs` console, plus its text
    file: access-log.png
    console: logs
    text: true
```

```yaml
- screenshot: true           # named after the step
```

## Common mistakes

- Without a display (`--headless`), the console text is saved (.html and .txt) instead of a PNG.
- Cropping to a console needs recording inside the machine (`record: guest`); host recording saves the whole VM window.
- For a screenshot at every chapter, set `defaults.screenshots.chapters` instead of adding steps.
