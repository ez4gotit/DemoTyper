from __future__ import annotations

import json
from pathlib import Path

import pytest

from scenarioplay.engine.context import RunOptions
from scenarioplay.engine.take import run_take
from scenarioplay.loader import load_scenario

FAST = """
defaults:
  typing: {profile: robot}
  after_command_pause: 0
  timeout: 15
"""


class Result:
    def __init__(self, code: int, out_dir: Path):
        self.code = code
        dirs = sorted(out_dir.iterdir())
        assert len(dirs) == 1, dirs
        self.dir = dirs[0]
        self.report = json.loads((self.dir / "report.json").read_text())
        self.log = (self.dir / "take.log").read_text()
        transcript = self.dir / "transcript" / "main.txt"
        self.transcript = transcript.read_text() if transcript.exists() else ""


@pytest.fixture
def play(write_scenario, tmp_path):
    """Play scenario text headless; `fast` prepends robot-speed defaults."""

    async def _play(text: str, *, fast: bool = True, **opts) -> Result:
        path = write_scenario((FAST if fast else "") + text)
        parsed, problems = load_scenario(path)
        assert parsed is not None, [p.format() for p in problems]
        out = tmp_path / "takes"
        settings = {"record": False, "headless": True, "speed": 4, **opts}
        options = RunOptions(out_dir=out, **settings)
        code = await run_take(parsed, options)
        return Result(code, out)

    return _play
