# `caption`

*Action.* Show a subtitle line for some seconds without starting a chapter.

## Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `caption` (main) | text | required | Subtitle text. |
| `duration` | number | `4.0` | Seconds the subtitle stays on screen. |

Every step also takes the [common options](index.md#common-options).

## Examples

```yaml
- caption: "nginx is listening on port 80"
```

```yaml
- caption: "This takes about a minute"
  duration: 6
```

## Common mistakes

- Captions go into subtitles.srt; they only appear in the video with `--burn-subtitles`.
