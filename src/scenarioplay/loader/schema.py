"""JSON Schema of the scenario format, built from the registered plugins (spec 14.2)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ..plugins import ACTIONS, CONDITIONS, load_plugins
from .model import Scenario

SCHEMA_ID = "https://scenarioplay.dev/schema/scenario-v1.json"
REF = "#/$defs/{model}"


def _add(defs: dict[str, Any], model: type[BaseModel]) -> dict[str, Any]:
    schema = model.model_json_schema(ref_template=REF)
    defs.update(schema.pop("$defs", {}))
    return schema


def build_schema() -> dict[str, Any]:
    load_plugins()
    defs: dict[str, Any] = {}

    cond_refs = []
    for keyword, cls in sorted(CONDITIONS.items()):
        schema = _add(defs, cls)
        schema["required"] = sorted(set(schema.get("required", [])) | {keyword})
        defs[cls.__name__] = schema
        cond_refs.append({"$ref": REF.format(model=cls.__name__)})
    defs["Condition"] = {
        "description": "A wait condition (spec section 7). A bare string is a regex.",
        "anyOf": [{"type": "string"}, *cond_refs],
    }
    cond_ref = {"$ref": "#/$defs/Condition"}

    step_refs = []
    for keyword, cls in sorted(ACTIONS.items()):
        schema = _add(defs, cls)
        schema["required"] = sorted(set(schema.get("required", [])) | {keyword})
        for field in cls.CONDITION_FIELDS:
            if field in schema.get("properties", {}):
                description = schema["properties"][field].get("description")
                schema["properties"][field] = {**cond_ref}
                if description:
                    schema["properties"][field]["description"] = description
        defs[cls.__name__] = schema
        step_refs.append({"$ref": REF.format(model=cls.__name__)})
    defs["Step"] = {"description": "One step: exactly one action keyword plus its options.",
                    "anyOf": step_refs}

    root = _add(defs, Scenario)
    for section in ("setup", "steps", "finally"):
        prop = root["properties"][section]
        prop["items"] = {"$ref": "#/$defs/Step"}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA_ID,
        **root,
        "title": "ScenarioPlay scenario",
        "$defs": dict(sorted(defs.items())),
    }
