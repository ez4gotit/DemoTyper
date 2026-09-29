"""Consoles on a second machine (spec 9.2): ssh runs inside the pane, so what is typed
still appears on the recorded screen. Logins are key-based (spec 13, security)."""

from __future__ import annotations

import os
import shlex

from ..loader.model import ConsoleSpec, SshSpec


def ssh_destination(spec: ConsoleSpec) -> str:
    assert spec.host
    user = spec.ssh.user if spec.ssh else None
    if user and "@" not in spec.host:
        return f"{user}@{spec.host}"
    return spec.host


def ssh_argv(spec: ConsoleSpec, *, tty: bool, batch: bool) -> list[str]:
    s = spec.ssh or SshSpec()
    argv = [s.program]
    if tty:
        argv.append("-t")
    argv += ["-o", "StrictHostKeyChecking=accept-new"]
    if batch:
        argv += ["-o", "BatchMode=yes"]
    if s.key:
        argv += ["-i", os.path.expanduser(s.key)]
    if s.port != 22:
        argv += ["-p", str(s.port)]
    argv += s.options
    argv.append(ssh_destination(spec))
    return argv


def remote_shell_command(spec: ConsoleSpec) -> str:
    """The pane command: log in, change to the console's directory, start a login shell."""
    parts = [f"cd {shlex.quote(spec.cwd) if spec.cwd != '~' else '~'} 2>/dev/null"]
    parts += [f"export {k}={shlex.quote(v)}" for k, v in spec.env.items()]
    parts.append("exec $SHELL -l")
    remote = "; ".join(parts)
    return "exec " + shlex.join([*ssh_argv(spec, tty=True, batch=False), remote])


def remote_run_argv(spec: ConsoleSpec, command: str, cwd: str | None = None) -> list[str]:
    """argv that runs `command` on the console's machine, out of view."""
    where = cwd or spec.cwd
    cd = f"cd {shlex.quote(where) if where != '~' else '~'} 2>/dev/null; "
    return [*ssh_argv(spec, tty=False, batch=True), cd + command]
