"""The `vmware` target (spec 4.1): the runner on the host, the scenario in a Linux guest.

prepare(): revert to `target.snapshot`, start the VM, wait for its IP (VMware Tools), wait
for SSH, then wait for the graphical session so the terminal can be shown and recorded.
"""

from __future__ import annotations

import asyncio
import getpass
import os
from collections.abc import Callable

from ..errors import EnvironmentProblem
from ..loader.model import SshSpec, TargetSpec
from ..transport.ssh import SSHTransport
from .vmrun import Vmrun

Log = Callable[[str, str], None]

# The Xauthority file of the logged-in desktop user: GDM on Xorg, then the classic one.
FIND_XAUTH = ('for f in "/run/user/$(id -u)/gdm/Xauthority" "$HOME/.Xauthority"; do '
              '[ -r "$f" ] && { echo "$f"; exit 0; }; done; exit 1')


class VMwareTarget:
    def __init__(self, spec: TargetSpec, log: Log, vmrun_path: str | None = None):
        assert spec.vmx
        self.spec = spec
        self.log = log
        self.vmrun = Vmrun(spec.vmx, log, vmrun_path or os.environ.get("SCENARIOPLAY_VMRUN"))
        self.ssh = spec.ssh or SshSpec()
        self.display = spec.recorder.display or ":0"
        self.transport: SSHTransport | None = None
        self.x_env: dict[str, str] = {}

    async def prepare(self) -> SSHTransport:
        if self.spec.snapshot:
            self.log("info", f"reverting the VM to snapshot {self.spec.snapshot!r}")
            await self.vmrun.revert(self.spec.snapshot)
        if not await self.vmrun.running():
            await self.vmrun.start(gui=self.spec.record == "host")
        return await self.wait_guest()

    async def wait_guest(self) -> SSHTransport:
        """Wait for the guest after a start, revert or reboot (spec 4.4): IP, SSH,
        desktop, all within target.boot_timeout."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.spec.boot_timeout

        def left() -> float:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise EnvironmentProblem(
                    f"the guest was not ready within boot_timeout ({self.spec.boot_timeout:g}s)")
            return remaining

        host = self.ssh.host
        if host == "auto":
            host = await self.vmrun.guest_ip(left())
            self.log("info", f"guest IP {host}")
        transport = SSHTransport(host, port=self.ssh.port,
                                 user=self.ssh.user or getpass.getuser(), key=self.ssh.key,
                                 known_hosts=self.ssh_known_hosts())
        await transport.wait_connect(left())
        self.log("info", f"connected over SSH to {transport.where}")
        await self._wait_desktop(transport, left)
        self.transport = transport
        return transport

    def ssh_known_hosts(self) -> str | None:
        value = self.ssh.known_hosts
        return None if value in (None, "", "none") else value

    async def _wait_desktop(self, transport: SSHTransport, left: Callable[[], float]) -> None:
        """The X server of the logged-in user must be up before the terminal opens."""
        number = self.display.lstrip(":").split(".")[0] or "0"
        while True:
            socket = await transport.run(["test", "-S", f"/tmp/.X11-unix/X{number}"])
            xauth = await transport.run(["sh", "-c", FIND_XAUTH])
            if socket.rc == 0:
                self.x_env = {"DISPLAY": self.display}
                if xauth.rc == 0 and xauth.out.strip():
                    self.x_env["XAUTHORITY"] = xauth.out.strip()
                self.log("info", f"guest desktop ready on {self.display}")
                return
            await asyncio.sleep(min(2.0, left()))

    async def restart(self, kind: str, snapshot: str | None) -> SSHTransport:
        """`vm: revert` / `vm: reboot` in the middle of a take (spec 4.4)."""
        if self.transport is not None:
            await self.transport.close()
            self.transport = None
        if kind == "revert":
            name = snapshot or self.spec.snapshot
            if not name:
                raise EnvironmentProblem("vm revert needs a snapshot name (`snapshot:` on the "
                                         "step or `target.snapshot`)")
            await self.vmrun.revert(name)
            if not await self.vmrun.running():
                await self.vmrun.start(gui=self.spec.record == "host")
        else:
            await self.vmrun.reset()
        return await self.wait_guest()
