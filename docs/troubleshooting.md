# Troubleshooting

Start with `scenarioplay doctor`, or `scenarioplay doctor --target vmware --vmx … --key …`
on a VMware host. Every failed take leaves `take.log` and `report.json`: the failing step
and its line, what it waited for, the last 50 lines of output, and a screenshot when
recording.

## A step timed out

`timed out after 60s waiting for the shell prompt`

- **The command really is slow:** raise `timeout` on that step.
- **The command never returns** (`tail -f`, a server, `watch`): use `type` with
  `enter: true` and a `wait_for` (`text`, `idle`) instead of `run`.
- **The command asked something** (`[Y/n]`, a password): add an `expect` or an answer rule.
  The last lines of output in the log show the question.
- **Waiting for `text` that is already on screen from before:** `text` only sees output
  since the last input. Use `scope: screen` if you mean the whole screen.

## "the prompt regex … does not match the shell prompt"

The take stops before the first step and prints the prompt line it saw. Set
`defaults.prompt` (or `prompt` on the console) to a regex that matches the end of that
line; see [the prompt regex](waiting.md#the-prompt-regex). Test it with
`scenarioplay run … --headless --no-record`.

## "the command line shows … instead of …; retyping it"

The line read back before Enter was not what was typed. The runner fixed it; the command
that ran was right. It happens with shell plugins that rewrite what's typed (zsh
autocorrect, auto-pairing brackets). Turn those off in the lab user's shell for recordings.

## The video is black

- **WSLg or another Wayland desktop:** the X display there is XWayland, which x11grab
  records as black. `doctor` warns about this. Record on an Xorg session (at the login
  screen, choose "Ubuntu on Xorg"), under Xvfb, or with `backend: wf-recorder` on wlroots
  desktops.
- **The screen locked or blanked during the take:** turn off screen blanking and locking
  in the guest ([setup](setup.md)).

## The terminal is not full screen, or text is cut off at the right

- **No window manager (bare Xvfb):** the terminal cannot go full screen. The log says
  `terminal window: WxH cells`. Set `target.terminal.command` with an explicit geometry
  that fits the screen.
- **A fixed geometry wider than the screen:** the right edge is cut off silently. At font
  size 13 a cell is about 11 px wide, so 1920 px fits about 172 columns.
- **Text too small in the video:** raise `target.terminal.font_size`. Around 18 at
  1920×1080 is readable.

## Layout looks wrong

- Panes appear in `consoles` order. `split-horizontal` puts them side by side and
  `split-vertical` stacks them.
- `size` only works in the two split layouts.
- `layout: single` with several consoles shows one at a time; `tabs` adds a tab bar.

## VMware

- **`vmrun not found`:** install Workstation, or set `SCENARIOPLAY_VMRUN` to `vmrun`'s path.
- **`vmrun getGuestIPAddress` fails:** open-vm-tools must run in the guest
  (`systemctl status open-vm-tools`).
- **`cannot connect over SSH`:**
  - sshd must run in the guest, and your key must be in the guest user's
    `authorized_keys`.
  - Check `target.ssh.user`, `key` and `port`.
  - A changed host key (a rebuilt VM) fails the check against `known_hosts`: remove the old
    entry, or set `known_hosts: none` for a throwaway lab VM.
- **The guest was not ready within `boot_timeout`:** raise `target.boot_timeout`. Auto-login
  must be on, so a desktop session exists without anyone at the keyboard.
- **The terminal does not appear in the guest:** the runner looks for `/tmp/.X11-unix/X0`
  and the user's Xauthority. Log in to an Xorg session (not Wayland) with auto-login.
- **`vm: revert` is rejected:** with `target.record: guest` it is only allowed in `setup`
  (spec 4.4). Use `record: host` for reverts in the middle of the video.

## Secrets

- **`missing secret X`:** give it as an environment variable or in a `--secrets` file.
- **`secrets cannot be shown in captions…` / `visible on screen`:** by design. Use a
  `secret` step or an answer rule to type a password.
- **`no hidden-input prompt … the secret was not typed`:** the program echoes what is
  typed, so the runner refused. Check that the program really asks for a password at that
  point.
