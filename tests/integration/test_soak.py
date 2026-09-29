"""`scenarioplay soak` (spec 13 reliability): several takes, same sequence of steps."""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from scenarioplay.soak import step_sequence

from ..conftest import ROOT

pytestmark = pytest.mark.integration


def test_step_sequence_ignores_typos_and_timing():
    a = {"steps": [{"path": "steps.0", "status": "ok", "notes": ["branch: then"]},
                   {"path": "steps.1", "status": "ok", "notes": ["  typo at 3 …"]}]}
    b = {"steps": [{"path": "steps.0", "status": "ok", "notes": ["branch: then"]},
                   {"path": "steps.1", "status": "ok", "notes": []}]}
    c = {"steps": [{"path": "steps.0", "status": "ok", "notes": ["branch: else"]},
                   {"path": "steps.1", "status": "ok", "notes": []}]}
    assert step_sequence(a) == step_sequence(b) != step_sequence(c)


def test_soak_three_takes_of_the_loops_example(tmp_path):
    example = ROOT / "examples" / "loops-and-conditions.yaml"
    proc = subprocess.run(
        [sys.executable, "-m", "scenarioplay.cli", "soak", str(example), "--takes", "3",
         "--headless", "--speed", "10", "--out", str(tmp_path / "soak"),
         "--var", "workdir=" + str(tmp_path / "work")],
        capture_output=True, text=True, timeout=600,
        env={**os.environ, "DEPLOY_TOKEN": "t0k3n"})
    assert proc.returncode == 0, proc.stdout + proc.stderr[-3000:]
    assert "3 takes: 3 succeeded" in proc.stdout
    assert "every take followed the same" in proc.stdout
