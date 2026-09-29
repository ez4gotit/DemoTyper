"""Phase 3 acceptance (spec 15): a 3-console demo (server, client, logs) runs with
`parallel`. Readability in the video is checked by recording it (see the plan's status)."""

from __future__ import annotations

import json
import random

import pytest

from scenarioplay.engine.context import RunOptions
from scenarioplay.engine.take import run_take
from scenarioplay.exitcodes import ExitCode
from scenarioplay.loader import load_scenario

from ..conftest import ROOT

pytestmark = pytest.mark.integration


async def test_multi_console_demo(tmp_path):
    port = random.randint(20000, 40000)
    site = str(tmp_path / "site")
    parsed, problems = load_scenario(ROOT / "examples" / "multi-console.yaml",
                                     extra_vars={"port", "site"})
    assert parsed is not None, [p.format() for p in problems]
    out = tmp_path / "takes"
    code = await run_take(parsed, RunOptions(
        record=False, headless=True, out_dir=out, speed=6,
        cli_vars={"port": port, "site": site}))
    take = next(out.iterdir())
    assert code == ExitCode.OK, (take / "take.log").read_text()

    def text(name):
        return (take / "transcript" / f"{name}.txt").read_text()

    assert "Serving HTTP" in text("server")
    assert [line for line in text("client").splitlines() if line in ("200", "404")] == \
        ["200", "200", "404"]
    assert '"GET /missing HTTP/1.1" 404' in text("logs")
    report = json.loads((take / "report.json").read_text())
    parallel = next(s for s in report["steps"] if s["action"] == "parallel")
    assert parallel["status"] == "ok"
