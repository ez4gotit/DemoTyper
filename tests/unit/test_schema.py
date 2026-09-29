from __future__ import annotations

import json

import jsonschema
import pytest
from ruamel.yaml import YAML

from scenarioplay.loader.schema import build_schema

from ..conftest import ROOT

SCHEMA_FILE = ROOT / "schema" / "scenarioplay.schema.json"


@pytest.fixture(scope="module")
def schema():
    s = build_schema()
    jsonschema.Draft202012Validator.check_schema(s)
    return s


def _yaml(path):
    return YAML(typ="safe").load(path.read_text(encoding="utf-8"))


def test_checked_in_schema_is_current(schema):
    """Regenerate with: scenarioplay schema > schema/scenarioplay.schema.json"""
    assert json.loads(SCHEMA_FILE.read_text(encoding="utf-8")) == schema


def test_examples_match_schema(schema):
    validator = jsonschema.Draft202012Validator(schema)
    for path in sorted((ROOT / "examples").glob("*.yaml")):
        errors = list(validator.iter_errors(_yaml(path)))
        assert not errors, f"{path.name}: {errors[0].message}"


def test_schema_rejects_unknown_step_and_top_key(schema):
    validator = jsonschema.Draft202012Validator(schema)
    assert not validator.is_valid({"steps": [{"pasue": 1}]})
    assert not validator.is_valid({"steps": [{"run": "ls"}], "stepz": []})
    assert not validator.is_valid({"steps": [{"run": "ls", "enter": True}]})
    assert validator.is_valid({"steps": [{"type": "y", "enter": True,
                                          "wait_for": {"prompt": True}}]})
