"""asciinema recordings, one per console (spec 10.3): `run --cast`.

tmux pipes each pane's output to a small helper that timestamps it in asciicast v2
format. The file starts with the pane's screen as it was when recording began, so it
matches the video's first frame.
"""

from __future__ import annotations

import json
import shlex
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .driver import Console

HELPER = r'''import codecs, json, os, sys, time
out, t0 = sys.argv[1], float(sys.argv[2])
dec = codecs.getincrementaldecoder("utf-8")("replace")
with open(out, "a", encoding="utf-8") as f:
    while True:
        data = os.read(0, 65536)
        if not data:
            break
        text = dec.decode(data)
        if text:
            f.write(json.dumps([round(time.time() - t0, 6), "o", text]) + "\n")
            f.flush()
'''


class CastRecorder:
    def __init__(self, runtime_dir: str):
        self.runtime_dir = runtime_dir
        self.helper = f"{runtime_dir}/cast_helper.py"
        self.files: dict[str, str] = {}  # console name -> cast file on the target

    async def start(self, console: Console, t0: float, title: str) -> None:
        transport = console.tmux.transport
        if not self.files:
            await transport.write_file(self.helper, HELPER)
        info = await console.info()
        path = f"{self.runtime_dir}/{console.name}.cast"
        screen = await console.tmux("capture-pane", "-p", "-e", "-t", console.pane)
        header = {"version": 2, "width": info.width, "height": info.height,
                  "timestamp": int(t0), "title": f"{title} - {console.name}",
                  "env": {"TERM": "screen-256color"}}
        first = [round(max(0.0, time.time() - t0), 6), "o",
                 "\x1b[H\x1b[2J" + screen.rstrip("\n").replace("\n", "\r\n")]
        await transport.write_file(path, json.dumps(header) + "\n" + json.dumps(first) + "\n")
        command = f"python3 {shlex.quote(self.helper)} {shlex.quote(path)} {t0:.6f}"
        await console.tmux("pipe-pane", "-o", "-t", console.pane, command)
        self.files[console.name] = path

    async def stop(self, console: Console) -> None:
        if console.name in self.files and not console.closed:
            await console.tmux("pipe-pane", "-t", console.pane, check=False)
