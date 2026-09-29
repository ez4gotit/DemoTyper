"""JSON Schema of the scenario format, built from the registered plugins (spec 14.2)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ..fielddocs import FIELD_DOCS
from ..plugins import ACTIONS, CONDITIONS, load_plugins
from .model import OnFailRetry, Scenario

SCHEMA_ID = "https://scenarioplay.dev/schema/scenario-v1.json"
REF = "#/$defs/{model}"


def _add(defs: dict[str, Any], model: type[BaseModel]) -> dict[str, Any]:
    schema = model.model_json_schema(ref_template=REF)
    defs.update(schema.pop("$defs", {}))
    for key, prop in schema.get("properties", {}).items():
        if "description" not in prop and key in FIELD_DOCS:
            prop["description"] = FIELD_DOCS[key]  # editor tooltips
    return schema


def build_schema() -> dict[str, Any]:
    load_plugins()
    defs: dict[str, Any] = {}

    step_list = {"type": "array", "items": {"$ref": "#/$defs/Step"}}
    cond_ref = {"$ref": "#/$defs/Condition"}
    check = {"description": "An expression such as `x == 1`, or a condition checked once.",
             "anyOf": [{"type": "string"}, {"type": "boolean"}, cond_ref]}

    def replace(props: dict[str, Any], key: str, new: dict[str, Any]) -> None:
        if key in props:
            description = props[key].get("description")
            props[key] = {**new, **({"description": description} if description else {})}

    cond_refs = []
    for keyword, cls in sorted(CONDITIONS.items()):
        schema = _add(defs, cls)
        schema["required"] = sorted(set(schema.get("required", [])) | {keyword})
        props = schema.get("properties", {})
        if keyword in ("any", "all"):
            replace(props, keyword, {"type": "array", "items": cond_ref})
        replace(props, "on_timeout", {"anyOf": [
            {"enum": ["fail", "continue", "retry"]}, step_list]})
        defs[cls.__name__] = schema
        cond_refs.append({"$ref": REF.format(model=cls.__name__)})
    defs["Condition"] = {
        "description": "A wait condition (spec section 7). A bare string is a regex.",
        "anyOf": [{"type": "string"}, *cond_refs],
    }

    step_refs = []
    for keyword, cls in sorted(ACTIONS.items()):
        schema = _add(defs, cls)
        schema["required"] = sorted(set(schema.get("required", [])) | {keyword})
        props = schema.get("properties", {})
        for field in cls.CONDITION_FIELDS:
            replace(props, field, cond_ref)
        for field in ("when", *cls.CHECK_FIELDS):
            replace(props, field, check)
        for field in cls.STEP_LIST_FIELDS:
            replace(props, field, step_list)
        if keyword == "if":
            replace(props, "elif", {"type": "array", "items": {
                "type": "object", "additionalProperties": False, "required": ["if", "then"],
                "properties": {"if": check, "then": step_list}}})
        replace(props, "on_fail", {"anyOf": [
            {"enum": ["fail", "continue"]}, {"$ref": "#/$defs/OnFailRetry"}, step_list]})
        defs[cls.__name__] = schema
        step_refs.append({"$ref": REF.format(model=cls.__name__)})
    defs["Step"] = {"description": "One step: exactly one action keyword plus its options.",
                    "anyOf": step_refs}
    defs["OnFailRetry"] = OnFailRetry.model_json_schema(ref_template=REF)

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
