# Setting up

## The machine that is recorded (local target, or the VMware guest)

Reference systems: Ubuntu 22.04/24.04, Debian 12, Rocky/Alma 9. Use an **Xorg** desktop
session; Wayland sessions record black with x11grab.

```bash
# Ubuntu / Debian
sudo apt install tmux ffmpeg xterm fonts-dejavu-core
# Rocky / Alma (ffmpeg from RPM Fusion)
sudo dnf install tmux xterm dejavu-sans-mono-fonts ffmpeg
```

That is all the runner needs in the guest: tmux 3.0+, a terminal emulator and a recorder.
For the vmware target, also sshd and open-vm-tools (usually preinstalled).

Settings for good videos:

- **Resolution:** 1920×1080, at 100 % scaling.
- **Terminal font:** a monospace font at 16–20 px (`target.terminal.font_size`). About 100
  columns per full-width pane is readable.
- **Screen:** no screen blanking or locking (GNOME: Settings → Privacy → Screen Lock off,
  and Power → Blank Screen: Never).
- **Notifications:** no pop-ups (GNOME: Do Not Disturb on).
- **Login:** auto-login for the lab user, so a desktop session exists after every revert.
- **Prompt:** keep the shell prompt simple, or set `defaults.prompt` to match it.
- **Shell:** turn off features that rewrite typed text (zsh autocorrect, auto-pairing).

For the vmware target, log in once as the lab user with the settings above, then take the
snapshot named in `target.snapshot`.

Check with `scenarioplay doctor` on the Linux machine.

## The VMware host (Windows 10/11 or Linux)

1. Install VMware Workstation 17. `vmrun` comes with it and is found automatically, or set
   `SCENARIOPLAY_VMRUN`.
2. Install Python 3.10+ and ScenarioPlay: `pipx install .` (or `pip install -e .`).
3. Create an SSH key and install it in the guest:

   ```bash
   ssh-keygen -t ed25519 -f ~/.ssh/lab
   ssh-copy-id -i ~/.ssh/lab.pub student@<guest-ip>
   ```

4. For host-side recording (`target.record: host`, needed for `vm: revert` mid-take),
   install ffmpeg on the host. Windows uses gdigrab (the Workstation window must be visible
   and not covered); Linux uses x11grab.
5. Check:

   ```bash
   scenarioplay doctor --target vmware --vmx "D:/VMs/ubuntu/ubuntu.vmx" --key ~/.ssh/lab
   ```

A VMware scenario's `target`:

```yaml
target:
  kind: vmware
  vmx: "D:/VMs/ubuntu/ubuntu.vmx"
  snapshot: clean
  ssh: { host: auto, user: student, key: ~/.ssh/lab }
  record: guest            # or host
```
