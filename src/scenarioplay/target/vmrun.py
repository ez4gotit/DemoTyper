"""VMware Workstation control through `vmrun` (spec 4.2): start, stop, revert, snapshot,
guest IP. The host may be Windows or Linux."""

from __future__ import annotations

import asyncio
import os
import re
import shutil
from collections.abc import Callable

from ..errors import EnvironmentProblem

WINDOWS_PATHS = [
    r"C:\Program Files (x86)\VMware\VMware Workstation\vmrun.exe",
    r"C:\Program Files\VMware\VMware Workstation\vmrun.exe",
]
LINUX_PATHS = ["/usr/bin/vmrun", "/usr/local/bin/vmrun"]


def find_vmrun(explicit: str | None = None) -> str | None:
    if explicit:
        return explicit if os.path.exists(explicit) or shutil.which(explicit) else None
    found = shutil.which("vmrun")
    if found:
        return found
    for path in (*WINDOWS_PATHS, *LINUX_PATHS):
        if os.path.exists(path):
            return path
    return None


def display_name(vmx: str) -> str | None:
    """The VM's name as Workstation shows it (`displayName` in the .vmx)."""
    try:
        with open(vmx, encoding="utf-8", errors="replace") as f:
            for line in f:
                m = re.match(r'\s*displayName\s*=\s*"(.*)"', line)
                if m:
                    return m.group(1)
    except OSError:
        return None
    return None


class Vmrun:
    def __init__(self, vmx: str, log: Callable[[str, str], None], path: str | None = None):
        found = find_vmrun(path)
        if found is None:
            raise EnvironmentProblem("vmrun (VMware Workstation) not found; install Workstation "
                                     "or set SCENARIOPLAY_VMRUN to its path")
        self.path = found
        self.vmx = vmx
        self.log = log

    async def run(self, *args: str, timeout: float = 300.0) -> str:
        """vmrun -T ws <args>; vmrun reports errors on stdout as `Error: ...`."""
        self.log("info", f"vmrun {' '.join(args)}")
        proc = await asyncio.create_subprocess_exec(
            self.path, "-T", "ws", *args, stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise EnvironmentProblem(f"vmrun {args[0]} did not finish within {timeout:.0f}s") \
                from None
        text = out.decode(errors="replace").strip()
        if proc.returncode != 0 or text.startswith("Error:"):
            raise EnvironmentProblem(f"vmrun {args[0]} failed: {text or proc.returncode}")
        return text

    async def start(self, gui: bool) -> None:
        await self.run("start", self.vmx, "gui" if gui else "nogui")

    async def stop(self, hard: bool = False) -> None:
        await self.run("stop", self.vmx, "hard" if hard else "soft")

    async def reset(self) -> None:
        await self.run("reset", self.vmx, "soft")

    async def revert(self, snapshot: str) -> None:
        await self.run("revertToSnapshot", self.vmx, snapshot)

    async def snapshot(self, name: str) -> None:
        await self.run("snapshot", self.vmx, name)

    async def snapshots(self) -> list[str]:
        out = await self.run("listSnapshots", self.vmx, timeout=60)
        return [line.strip() for line in out.splitlines()[1:] if line.strip()]

    async def running(self) -> bool:
        out = await self.run("list", timeout=60)
        vmx = os.path.normcase(os.path.abspath(self.vmx))
        return any(os.path.normcase(os.path.abspath(line.strip())) == vmx
                   for line in out.splitlines()[1:])

    async def guest_ip(self, timeout: float) -> str:
        """Waits for VMware Tools (open-vm-tools) in the guest to report an address."""
        out = await self.run("getGuestIPAddress", self.vmx, "-wait", timeout=timeout)
        ip = out.strip().splitlines()[-1].strip() if out.strip() else ""
        if not re.fullmatch(r"[0-9a-fA-F.:]+", ip) or ip in ("unknown", "0.0.0.0"):
            raise EnvironmentProblem(f"vmrun getGuestIPAddress gave {out!r}; are "
                                     "open-vm-tools running in the guest?")
        return ip
