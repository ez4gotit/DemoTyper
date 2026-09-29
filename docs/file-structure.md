# File structure

A scenario is one UTF-8 YAML file with up to ten top-level keys. Only `steps` is required;
any other key is an error.

```yaml
version: 1                      # format version (default 1)
meta:                           # informational only
  title: "Lab 3 - Nginx setup"  # used for the take folder name and the .cast titles
  source_pdf: lab3.pdf
  author: "…"
target:                         # where to run and how to record (default: local)
  kind: local                   # local | vmware
defaults:                       # typing, prompt, timeouts, failure policy, answers
  typing: { profile: normal }
layout: single                  # how consoles are arranged (default: single)
consoles:                       # named consoles (default: one called `main`)
  - { name: main }
vars:                           # variables
  site: example.local
setup: []                       # steps before recording starts (not in the video)
steps: []                       # the recorded scenario
finally: []                     # steps that always run at the end (not in the video)
```

`include`, `define` and `call` are steps, not top-level keys.

## `target`

| Key | Default | Meaning |
| --- | --- | --- |
| `kind` | `local` | `local`: the runner runs on the Linux machine it types into. `vmware`: the runner runs on the host and reaches a Linux guest over SSH. |
| `vmx` | | Path of the VM's `.vmx` file (vmware). |
| `snapshot` | | Snapshot to revert to before every take (vmware); makes takes repeatable. |
| `ssh` | | `{host: auto, user, key, port: 22, known_hosts}`. `host: auto` asks VMware Tools for the guest's IP. |
| `record` | `guest` | Where the recorder runs: `guest` (inside the machine, native resolution) or `host` (captures the Workstation window; needed for `vm: revert/reboot` mid-take). |
| `boot_timeout` | `180` | Seconds to wait for the guest after a start, revert or reboot. |
| `terminal` | | `{command, font: Monospace, font_size: 16}`. Without `command`, the first installed of xterm, alacritty, kitty, gnome-terminal, xfce4-terminal and konsole. |
| `recorder` | | `{backend: auto, display, fps: 30, crf: 23, codec: libx264, preset: veryfast, lead_in: 2, tail: 2, draw_mouse: false}`. |

## `defaults`

| Key | Default | Meaning |
| --- | --- | --- |
| `typing` | profile `normal` | Speed and realism; see [typing](typing.md). |
| `prompt` | `[$#%>] ?$` | Regex for the end of the shell prompt. |
| `timeout` | `60` | Seconds a wait may take before the step fails. |
| `interval` | `0.2` | Seconds between screen checks. |
| `after_command_pause` | `1.0` | Pause after each `run`, so viewers can read the output. |
| `on_fail` | `fail` | `fail`, `continue` or `{retry: N, delay: S}`. |
| `keep_video_on_fail` | `true` | Keep the video of a failed take. |
| `clear_after_setup` | `true` | Clear the consoles after `setup`, so the video starts clean. |
| `answers` | `[]` | Prompts answered automatically, such as the sudo password. |

## `consoles`

| Key | Default | Meaning |
| --- | --- | --- |
| `name` | required | How steps refer to the console. |
| `title` | the name | Shown on the pane border or tab. |
| `shell` | `bash` | `bash`, `zsh` or `sh` (`sh` has no exit codes). |
| `cwd` | `~` | Starting directory. |
| `prompt` | `defaults.prompt` | This console's prompt regex. |
| `env` | `{}` | Extra environment variables. |
| `typing` | | Typing settings for this console. |
| `answers` | `[]` | Answer rules for this console (checked before `defaults.answers`). |
| `host` / `ssh` | | Run this console on another machine over ssh. |
| `size` | | Pane size in split layouts: `30%` or a number of cells. |
| `start` | `true` | `false`: open later with `open_console`. |

## `vars`, `setup`, `steps`, `finally`

- **`vars`:** variables for `{{ }}` templates and conditions; see [variables](language.md#variables).
- **`setup`:** runs before recording at full speed. Put cleanup and preparation here.
- **`steps`:** what the video shows.
- **`finally`:** always runs, even after a failure or Ctrl+C, and is not recorded.
