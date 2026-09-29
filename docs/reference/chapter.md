# `chapter`

*Action.* Start a chapter: video chapter marker, subtitle and log section.

## Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `chapter` (main) | text | required | Chapter title (also a subtitle and a line in chapters.txt). |
| `caption` | text | - | Subtitle text. |

Every step also takes the [common options](index.md#common-options).

## Examples

```yaml
- chapter: "Task 1: Install nginx"
```

```yaml
- chapter: "Task 2: Configure the site"
  caption: "The config lives in /etc/nginx/sites-available"
```

## Common mistakes

- Secrets are refused in chapter titles and captions.
- Chapters in `setup` or `finally` are only logged; those sections are not recorded.
