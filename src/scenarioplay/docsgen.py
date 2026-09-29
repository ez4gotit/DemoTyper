"""Generate the reference pages of the wiki (spec 14.3, item 3) from the code and
docs/reference.yaml: one page per action and control block, plus the wait conditions.

    scenarioplay gen-docs            # writes docs/reference/
"""

from __future__ import annotations

import re
import types
import typing
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from pydantic_core import PydanticUndefined
from ruamel.yaml import YAML

from .fielddocs import FIELD_DOCS
from .plugins import ACTIONS, CONDITIONS, load_plugins

COMMON = ("console", "timeout", "on_fail", "when", "label")
COND_COMMON = ("timeout", "interval", "scope", "on_timeout", "console", "as")

BLOCKS = {"if", "for_each", "repeat", "while", "until", "retry", "try", "define", "call",
          "break", "continue", "stop", "parallel", "include"}


def type_name(annotation: Any) -> str:
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)
    if origin is typing.Annotated:
        return type_name(args[0])
    if origin in (typing.Union, types.UnionType):
        # Optional fields: "null" says nothing the Default column doesn't.
        parts = [type_name(a) for a in args if a is not type(None)]
        return " or ".join(dict.fromkeys(parts))
    if origin is typing.Literal:
        return " / ".join(f"`{a}`" if not isinstance(a, bool) else str(a).lower() for a in args)
    if origin in (list, tuple):
        inner = ", ".join(type_name(a) for a in args if a is not Ellipsis)
        return f"list of {inner}" if origin is list else f"[{inner}]"
    if origin is dict:
        return "mapping"
    if annotation is type(None):
        return "null"
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return "mapping"
    names = {str: "text", int: "integer", float: "number", bool: "true/false",
             typing.Any: "anything"}
    return names.get(annotation, getattr(annotation, "__name__", str(annotation)))


def fields_table(model: type[BaseModel], skip: tuple[str, ...], main: str,
                 main_doc: str = "") -> list[str]:
    rows = ["| Option | Type | Default | Description |", "| --- | --- | --- | --- |"]
    for name, info in model.model_fields.items():
        key = info.alias or name
        if key in skip:
            continue
        if info.is_required():
            default = "required"
        elif info.default is PydanticUndefined or info.default is None:
            default = "-"
        else:
            value = info.default
            default = f"`{str(value).lower() if isinstance(value, bool) else value}`"
        text = info.description or (main_doc if key == main and main_doc else "") \
            or FIELD_DOCS.get(key, "")
        text = text.replace("\n", " ")
        text = text.replace("|", "\\|")
        label = f"`{key}`" + (" (main)" if key == main else "")
        rows.append(f"| {label} | {type_name(info.annotation)} | {default} | {text} |")
    return rows


def _doc(cls: type) -> str:
    text = (cls.__doc__ or "").strip()
    return re.sub(r"\s*\n\s*", " ", text)


def _examples(entry: dict[str, Any]) -> list[str]:
    out = []
    for ex in entry.get("examples", []):
        out += ["```yaml", ex.rstrip("\n"), "```", ""]
    return out


def action_page(keyword: str, cls: type[BaseModel], data: dict[str, Any],
                main_doc: str = "") -> str:
    kind = "Control block" if keyword in BLOCKS else "Action"
    lines = [f"# `{keyword}`", "", f"*{kind}.* {_doc(cls)}", "", "## Options", ""]
    lines += fields_table(cls, COMMON, keyword, main_doc)
    lines += ["", "Every step also takes the [common options](index.md#common-options)."
              + (" `when` is not allowed on blocks other than `break`, `continue` and `stop`."
                 if keyword in BLOCKS - {"break", "continue", "stop"} else ""), "",
              "## Examples", ""]
    lines += _examples(data)
    mistakes = data.get("mistakes", [])
    if mistakes:
        lines += ["## Common mistakes", ""] + [f"- {m}" for m in mistakes] + [""]
    return "\n".join(lines)


def conditions_page(data: dict[str, Any]) -> str:
    lines = ["# Wait conditions", "",
             "Used by `wait_for`, `expect`, and (checked once) by `if`, `while`, `until`, "
             "`assert` and `when`. See [choosing a wait](../waiting.md) for when to use which.",
             "", "Every condition also takes:", ""]
    base = CONDITIONS["prompt"]
    lines += fields_table(base, ("prompt",), "")
    for keyword, cls in sorted(CONDITIONS.items()):
        lines += ["", f"## `{keyword}`", "", _doc(cls), ""]
        own = [n for n, i in cls.model_fields.items() if (i.alias or n) not in COND_COMMON]
        if own:
            lines += fields_table(cls, COND_COMMON, keyword)
            lines.append("")
        lines += _examples(data.get(keyword, {}))
    return "\n".join(lines)


def index_page() -> str:
    from .actions.base import StepModel

    lines = ["# Reference", "", "One page per action and control block, generated from the "
             "code (options, types, defaults) and `docs/reference.yaml` (examples, mistakes).",
             "", "## Actions", ""]
    for kw in sorted(k for k in ACTIONS if k not in BLOCKS):
        lines.append(f"- [`{kw}`]({kw}.md): {_doc(ACTIONS[kw]).split('. ')[0].rstrip('.')}.")
    lines += ["", "## Control blocks", ""]
    for kw in sorted(k for k in ACTIONS if k in BLOCKS):
        lines.append(f"- [`{kw}`]({kw}.md): {_doc(ACTIONS[kw]).split('. ')[0].rstrip('.')}.")
    lines += ["", "## Wait conditions", "", "- [All conditions](conditions.md)", "",
              "## Common options", "", "Every step accepts these:", ""]
    lines += fields_table(StepModel, (), "")
    lines += ["", "- `console`: run in this console instead of the current one.",
              "- `timeout`: seconds for this step's wait (default `defaults.timeout`).",
              "- `on_fail`: `fail` (default), `continue`, `{retry: N, delay: S}`, or a list of "
              "recovery steps.",
              "- `when`: an expression or condition; the step is skipped when it is false.",
              "- `label`: a name for `--from`/`--to` and the log.", ""]
    return "\n".join(lines)


def generate(docs_dir: Path) -> dict[Path, str]:
    """All reference pages: path -> content."""
    load_plugins()
    data = YAML(typ="safe").load((docs_dir / "reference.yaml").read_text(encoding="utf-8"))
    out_dir = docs_dir / "reference"
    pages = {out_dir / "index.md": index_page()}
    for keyword, cls in sorted(ACTIONS.items()):
        pages[out_dir / f"{keyword}.md"] = action_page(
            keyword, cls, data["actions"].get(keyword, {}), data["main"].get(keyword, ""))
    pages[out_dir / "conditions.md"] = conditions_page(data["conditions"])
    return {p: text.rstrip("\n") + "\n" for p, text in pages.items()}


def write(docs_dir: Path) -> list[Path]:
    pages = generate(docs_dir)
    (docs_dir / "reference").mkdir(exist_ok=True)
    for path, text in pages.items():
        path.write_text(text, encoding="utf-8")
    return list(pages)
