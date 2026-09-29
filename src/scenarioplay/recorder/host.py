"""Recording mode B (spec 4.1): ffmpeg on the VMware host captures the VM's console.

On Windows it grabs the Workstation window with gdigrab (`title=<VM name> - VMware
Workstation`, or the whole `desktop`); on a Linux host, the host's X display. Recording on
the host keeps running through `vm: revert` and `vm: reboot` (spec 4.4).
"""

from __future__ import annotations

import sys
from pathlib import Path

from ..loader.model import RecorderSpec
from ..transport import LocalTransport
from .x11 import Log, X11Recorder


def default_source(vm_name: str | None) -> str:
    if sys.platform == "win32":
        return f"title={vm_name} - VMware Workstation" if vm_name else "desktop"
    import os

    return os.environ.get("DISPLAY", ":0")


class HostRecorder(X11Recorder):
    def __init__(self, spec: RecorderSpec, source: str, take_dir: Path, log: Log,
                 basename: str = "video"):
        super().__init__(spec, source, take_dir, log, transport=LocalTransport(),
                         basename=basename)
        self.windows = sys.platform == "win32"

    def grab_input(self) -> list[str]:
        if not self.windows:
            return super().grab_input()
        return ["-f", "gdigrab", "-framerate", str(self.spec.fps),
                "-draw_mouse", "1" if self.spec.draw_mouse else "0", "-i", self.display]

    async def _warn_if_black(self) -> None:
        if not self.windows:
            await super()._warn_if_black()

    async def screenshot(self, path: Path,
                         region: tuple[int, int, int, int] | None = None) -> bool:
        if region is not None:
            # The guest's pane sits somewhere inside the VM window, at an unknown offset.
            self.log("info", "host recording: screenshots show the whole VM window "
                             "(cropping to one console needs `record: guest`)")
        if not self.windows:
            return await super().screenshot(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        res = await self.transport.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "gdigrab",
             "-i", self.display, "-frames:v", "1", str(path)], timeout=15)
        return res.rc == 0 and path.exists()
