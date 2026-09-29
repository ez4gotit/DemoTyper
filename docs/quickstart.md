# Quick start (phase 1)

This page takes you from a lab task to a recorded video. The full syntax wiki arrives in
phase 4; this page covers what phase 1 supports.

## 1. Check the machine

```bash
scenarioplay doctor
```

You need tmux 3.0+, bash, ffmpeg with x11grab, an X display (`$DISPLAY`) and a terminal
emulator (xterm, alacritty, kitty, gnome-terminal, xfce4-terminal or konsole).

## 2. Write the scenario

One PDF task becomes one `chapter`. Each command becomes a `run` step.

```yaml
version: 1
meta: { title: "Lab 1 - Files" }
defaults:
  typing: { profile: normal }      # novice | normal | expert | robot
setup:                             # runs before recording; not in the video
  - run: "rm -rf ~/lab1"
steps:
  - chapter: "Task 1: Create a folder"
  - run: "mkdir ~/lab1 && cd ~/lab1"
  - chapter: "Task 2: Create a file"
    caption: "printf writes two lines"
  - run: "printf 'a\\nb\\n' > notes.txt"
  - run: "wc -l notes.txt"
    expect: '^2 notes\.txt$'       # wait for this output instead of the prompt
finally:                           # always runs at the end; not in the video
  - run: "cd ~"
```

## 3. Check it and rehearse it

```bash
scenarioplay validate lab1.yaml            # errors come with line numbers
scenarioplay run lab1.yaml --dry-run       # what will be typed and awaited
scenarioplay run lab1.yaml --no-record     # watch it play, no video
scenarioplay run lab1.yaml --no-record --speed 3   # faster rehearsal
```

## 4. Record

```bash
scenarioplay run lab1.yaml
```

The take folder is printed at the end, for example `takes/lab-1-files-20260929-141500-ab12/`.

## Passwords (sudo and others)

Don't type a password with `run` or `type`. It would land in the log in plain text, and it
could appear on screen. Add an answer rule instead, and every `sudo` command stays one line:

```yaml
defaults:
  answers:
    - when: '\[sudo\] password for'   # regex for the prompt, matched at the cursor
      secret: SUDO_PASS               # the secret's name, never its value
steps:
  - run: "sudo apt-get update"        # the prompt is answered whenever it appears
```

Give the value when you run the take, in either of two ways:

```bash
SUDO_PASS='...' scenarioplay run lab.yaml       # environment variable
scenarioplay run lab.yaml --secrets secrets.yaml  # file with "SUDO_PASS: ..." (chmod 600)
```

What the runner guarantees:

- The secret is typed only while the terminal hides input, as a password prompt does.
  If the prompt echoes, the secret isn't typed and the step times out.
- A wrong password fails the step straight away with "the secret was not accepted". sudo
  doesn't get to ask three times on camera.
- The value is replaced by `****` in the log, report, transcripts and subtitles. `validate`
  rejects secrets in `chapter`, `caption` and `log`.
- A missing secret stops the take before anything starts. `validate` lists the secrets a
  scenario needs.

Answers also work for questions: `{when: 'Continue\? \[Y/n\]', text: "y"}`. Rules can go in
`defaults.answers` for all consoles or in a console's own `answers`.

To type a secret explicitly at one point, use the `secret` step:
`- secret: DB_PASS` with `enter: true`.

sudo remembers the password for about 15 minutes per terminal. To show the prompt in the
video, put `sudo -k` at the end of `setup`.

## Phase 1 actions

| Step | What it does |
| --- | --- |
| `run: "cmd"` | Types the command, presses Enter, waits for the prompt. Options: `expect`, `wait_for`, `check_exit`, `timeout`, `typing`. |
| `type: "text"` | Types text without Enter. Options: `enter: true`, `enter_newlines: true`, `wait_for`. |
| `enter: true` | Presses Enter (`enter: 3` presses it three times). |
| `key: C-c` | Sends a key: `C-c`, `C-d`, `C-l`, `Tab`, `Up`, `Down`, `Escape`, `F1`–`F12`, `M-x`, `PageDown`… Option `repeat`. |
| `wait_for: {…}` | Waits for `prompt: true`, `text: "…"` or `regex: "…"`. Options: `timeout`, `interval`, `scope`, `on_timeout`. |
| `pause: 2` | Waits 2 seconds (scaled by `--speed`). |
| `chapter: "Title"` | New chapter: video marker, subtitle, log section. Option `caption`. |
| `caption: "Text"` | A subtitle for `duration` seconds (default 4). |
| `secret: NAME` | Types a secret into a password prompt. Options: `enter: true`, `hidden: false` (drops the hidden-input check). |
| `clear: command` | Types `clear` (`clear: key` sends Ctrl+L). |
| `screenshot: name.png` | Saves a screenshot into the take folder. |
| `log: "text"` | Writes a line to the take log only. |

Every step also accepts `console`, `timeout`, `on_fail: fail | continue` and `label`.

## Common mistakes

- **"the prompt regex … does not match"**: your prompt doesn't end in `$`, `#`, `%` or
  `>`. Set `defaults.prompt` to a regex matching the end of your prompt.
- **A `run` that never returns** (`tail -f`, a server): use `type` with `enter: true`
  and `wait_for: {text: "…"}`, then `key: C-c`.
- **`expect` matches too early**: `expect` only looks at output produced after the Enter,
  never at the typed command itself.
