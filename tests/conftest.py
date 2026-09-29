from __future__ import annotations

import shutil
import sys
import textwrap
from pathlib import Path

import pytest

from scenarioplay.loader import ParsedScenario, load_scenario

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"

HAVE_TMUX = sys.platform == "linux" and shutil.which("tmux") and shutil.which("bash")


def pytest_collection_modifyitems(config, items):
    skip = pytest.mark.skip(reason="needs Linux with tmux and bash")
    for item in items:
        if "integration" in item.keywords and not HAVE_TMUX:
            item.add_marker(skip)


@pytest.fixture
def write_scenario(tmp_path):
    """Write YAML text (dedented) to a file and return its path."""

    def _write(text: str, name: str = "scenario.yaml") -> Path:
        path = tmp_path / name
        path.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")
        return path

    return _write


@pytest.fixture
def load(write_scenario):
    """Load YAML text; returns (parsed or None, problems)."""

    def _load(text: str) -> tuple[ParsedScenario | None, list]:
        return load_scenario(write_scenario(text))

    return _load
