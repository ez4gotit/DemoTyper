"""Phase 2 acceptance (spec 15): the loops-and-conditions example takes both branches
correctly under two variable sets, and no secret appears in any output."""

from __future__ import annotations

import json

import pytest
from ruamel.yaml import YAML

from scenarioplay.engine.context import RunOptions
from scenarioplay.engine.take import run_take
from scenarioplay.exitcodes import ExitCode
from scenarioplay.loader import load_scenario

from ..conftest import ROOT

pytestmark = pytest.mark.integration

EXAMPLE = ROOT / "examples" / "loops-and-conditions.yaml"
TOKEN = "tok-Ae7!q9 z"


async def _take(tmp_path, name, vars_file=None):
    file_vars = YAML(typ="safe").load(vars_file.read_text()) if vars_file else {}
    parsed, problems = load_scenario(EXAMPLE, extra_vars=set(file_vars))
    assert parsed is not None, [p.format() for p in problems]
    out = tmp_path / name
    code = await run_take(parsed, RunOptions(record=False, headless=True, out_dir=out,
                                             speed=8, vars_file=file_vars))
    take = next(out.iterdir())
    return code, take


def _all_bytes(take):
    return [(p.name, p.read_bytes()) for p in take.rglob("*") if p.is_file()]


@pytest.mark.parametrize("variant", ["dev", "prod"])
async def test_both_variable_sets(tmp_path, monkeypatch, variant):
    monkeypatch.setenv("DEPLOY_TOKEN", TOKEN)
    vars_file = ROOT / "examples" / "vars" / "prod.yaml" if variant == "prod" else None
    code, take = await _take(tmp_path, variant, vars_file)
    report = json.loads((take / "report.json").read_text())
    transcript = (take / "transcript" / "main.txt").read_text()
    assert code == ExitCode.OK, (take / "take.log").read_text()

    if_step = next(s for s in report["steps"] if s["action"] == "if")
    if variant == "prod":
        assert if_step["notes"] == ["branch: then"]
        assert "replicas=3" in transcript and "debug=true" not in transcript
        assert "Production runs 3 replicas" in (take / "subtitles.srt").read_text()
        assert "4" in [line.strip() for line in transcript.splitlines()]  # four services
    else:
        assert if_step["notes"] == ["branch: else"]
        assert "debug=true" in transcript and "replicas=" not in transcript
        assert "3" in [line.strip() for line in transcript.splitlines()]
    assert f"Task 1: Create the {variant} services" in (take / "chapters.txt").read_text()
    assert "deploy accepted" in transcript
    for name, data in _all_bytes(take):
        assert TOKEN.encode() not in data, f"secret found in {name}"
