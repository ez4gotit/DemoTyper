"""`scenarioplay doctor`: check the machine is ready for takes (spec section 11)."""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass

from .console.terminal import find_terminal
from .console.tmux import MIN_VERSION, parse_version
from .recorder.x11 import BLACK_WARNING, screen_is_black


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    required: bool = True


def _run(argv: list[str], timeout: float = 10) -> tuple[int, str]:
    try:
        res = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return 127, str(e)
    return res.returncode, (res.stdout + res.stderr).strip()


def run_host_checks(vmx: str | None, key: str | None) -> list[Check]:
    """The VMware host side (spec 4): vmrun, the VM, ssh key, and ffmpeg for mode B.
    The guest itself is checked when a take starts (tmux, terminal, desktop, recorder)."""
    from .target.vmrun import find_vmrun

    checks = [Check("Python 3.10+", sys.version_info >= (3, 10), sys.version.split()[0])]
    try:
        import asyncssh

        checks.append(Check("asyncssh", True, asyncssh.__version__))
    except ImportError:
        checks.append(Check("asyncssh", False, "not installed (pip install asyncssh)"))
    vmrun = find_vmrun(os.environ.get("SCENARIOPLAY_VMRUN"))
    checks.append(Check("vmrun", bool(vmrun), vmrun or "not found (install VMware "
                                                         "Workstation or set SCENARIOPLAY_VMRUN)"))
    if vmrun:
        rc, out = _run([vmrun, "-T", "ws", "list"], timeout=60)
        checks.append(Check("vmrun list", rc == 0, out.splitlines()[0] if out else str(rc)))
    if vmx:
        exists = os.path.exists(vmx)
        checks.append(Check(f"VM {vmx}", exists, "found" if exists else "no such file"))
        if exists and vmrun:
            rc, out = _run([vmrun, "-T", "ws", "listSnapshots", vmx], timeout=60)
            snaps = [s.strip() for s in out.splitlines()[1:] if s.strip()]
            checks.append(Check("snapshots", rc == 0, ", ".join(snaps) or "none",
                                required=False))
    if key:
        path = os.path.expanduser(key)
        checks.append(Check(f"ssh key {key}", os.path.exists(path),
                            "found" if os.path.exists(path) else "missing"))
    grabber = "gdigrab" if sys.platform == "win32" else "x11grab"
    rc, out = _run(["ffmpeg", "-hide_banner", "-devices"])
    checks.append(Check(f"ffmpeg with {grabber} (host recording, mode B)",
                        rc == 0 and grabber in out, "ok" if rc == 0 and grabber in out
                        else "missing", required=False))
    return checks


def run_checks(display: str | None) -> list[Check]:
    checks = [Check("Python 3.10+", sys.version_info >= (3, 10), sys.version.split()[0]),
              Check("Linux", sys.platform == "linux", sys.platform)]

    rc, out = _run(["tmux", "-V"])
    if rc == 0:
        version = parse_version(out)
        checks.append(Check("tmux 3.0+", version >= MIN_VERSION, out))
    else:
        checks.append(Check("tmux 3.0+", False, "not found"))

    for shell in ("bash", "zsh"):
        path = shutil.which(shell)
        checks.append(Check(shell, bool(path), path or "not found", required=shell == "bash"))

    lang = os.environ.get("LC_ALL") or os.environ.get("LC_CTYPE") or os.environ.get("LANG", "")
    checks.append(Check("UTF-8 locale", "UTF-8" in lang.upper() or "UTF8" in lang.upper(),
                        lang or "(unset; tmux children get C.UTF-8)", required=False))

    rc, out = _run(["ffmpeg", "-hide_banner", "-devices"])
    checks.append(Check("ffmpeg with x11grab", rc == 0 and "x11grab" in out,
                        "ok" if rc == 0 and "x11grab" in out else "missing"))
    checks.append(Check("ffprobe", bool(shutil.which("ffprobe")),
                        shutil.which("ffprobe") or "not found"))

    display = display or os.environ.get("DISPLAY")
    if display:
        rc, out = _run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "x11grab",
                        "-i", display, "-frames:v", "1", "-f", "null", "-"], timeout=15)
        checks.append(Check(f"capture display {display}", rc == 0,
                            "ok" if rc == 0 else out.splitlines()[-1] if out else "failed"))
        if rc == 0:
            black = asyncio.run(screen_is_black(display))
            checks.append(Check("captured screen has content", black is False,
                                BLACK_WARNING if black else "ok", required=False))
    else:
        checks.append(Check("X display", False, "$DISPLAY is not set (--no-record still works)"))

    terminal = find_terminal()
    checks.append(Check("terminal emulator", bool(terminal),
                        terminal or "none of xterm, alacritty, kitty, gnome-terminal, "
                                    "xfce4-terminal, konsole (or set target.terminal.command)"))
    return checks
