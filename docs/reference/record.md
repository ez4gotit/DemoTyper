# `record`

*Action.* Control the video at any point. `pause` / `resume` cut a stretch out of the current video (e.g. a long download); on resume a caption says how much time was skipped. `stop` / `start` end the current video file and begin a new one: a take with several clips writes clips/NN-name.mp4, each with its own chapters and subtitles. With `target.recorder.autostart: false`, nothing is recorded until the first `record: start`.

## Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `record` (main) | `pause` / `resume` / `start` / `stop` | required | pause, resume, start or stop. |
| `caption` | true/false | `true` | On resume: add a subtitle saying how much time was skipped. |
| `clip` | text | - | On start: a name for the new clip (used in its file name). |

Every step also takes the [common options](index.md#common-options).

## Examples

```yaml
- record: pause
- run: "sudo apt-get dist-upgrade -y"
  timeout: 1800
- record: resume             # adds a "(12 min 05 s skipped)" subtitle
```

```yaml
# target.recorder.autostart: false - nothing is recorded before this
- run: "cd ~/lab && git pull"
- record: start
  clip: install
- run: "make install"
- record: stop               # clips/01-install.mp4
- run: "make test"           # not in any video
- record: start
  clip: results              # clips/02-results.mp4
- run: "cat report.txt"
```

## Common mistakes

- `pause`/`resume` cuts time out of one video. `stop`/`start` makes separate video files, each with its own chapters and subtitles.
- Pausing twice, starting while recording, or stopping when nothing records only logs a warning.
- A chapter step that runs while recording is stopped opens the next clip at 0:00.
