"""YAML loading that keeps the line and column of every node."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

from ..errors import Location, Problem, ScenarioInvalid

YamlPath = tuple[Any, ...]


class LocMap:
    """Maps a path inside the document, such as ("steps", 3, "wait_for"), to its position."""

    def __init__(self, file: str):
        self.file = file
        self._pos: dict[YamlPath, tuple[int, int]] = {}

    def set(self, path: YamlPath, line: int, col: int) -> None:
        self._pos[path] = (line, col)

    def get(self, path: YamlPath) -> Location | None:
        """Position of `path`, or of its nearest ancestor that has one."""
        path = tuple(path)
        while True:
            if path in self._pos:
                line, col = self._pos[path]
                return Location(self.file, line, col)
            if not path:
                return None
            path = path[:-1]


def load_yaml(path: Path) -> tuple[Any, LocMap]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        raise ScenarioInvalid(
            [Problem(f"file is not valid UTF-8: {e}", Location(str(path), 1, 1))]) from None
    except OSError as e:
        raise ScenarioInvalid([Problem(f"cannot read file: {e.strerror}")]) from None

    yaml = YAML(typ="rt")
    yaml.allow_duplicate_keys = False
    try:
        doc = yaml.load(text)
    except Exception as e:  # ruamel raises many error classes; all carry marks
        mark = getattr(e, "problem_mark", None) or getattr(e, "context_mark", None)
        loc = Location(str(path), mark.line + 1, mark.column + 1) if mark else None
        problem = getattr(e, "problem", None) or str(e).splitlines()[0]
        context = getattr(e, "context", None)
        message = f"YAML syntax: {context + ', ' if context else ''}{problem}"
        raise ScenarioInvalid([Problem(message, loc)]) from None

    locs = LocMap(str(path))
    locs.set((), 1, 1)
    return _plain(doc, (), locs), locs


def _plain(node: Any, path: YamlPath, locs: LocMap) -> Any:
    """Convert ruamel's round-trip types to plain Python values, recording positions."""
    if isinstance(node, CommentedMap):
        out: dict[Any, Any] = {}
        for key, value in node.items():
            k = _scalar(key)
            try:
                line, col = node.lc.key(key)
                locs.set(path + (k,), line + 1, col + 1)
            except (KeyError, TypeError):
                pass
            out[k] = _plain(value, path + (k,), locs)
        return out
    if isinstance(node, CommentedSeq):
        items = []
        for i, value in enumerate(node):
            try:
                line, col = node.lc.item(i)
                locs.set(path + (i,), line + 1, col + 1)
            except (KeyError, TypeError, IndexError):
                pass
            items.append(_plain(value, path + (i,), locs))
        return items
    return _scalar(node)


def _scalar(value: Any) -> Any:
    if value is None or isinstance(value, bool):
        return value
    # ruamel wraps booleans, ints and floats in subclasses that keep formatting.
    type_name = type(value).__name__
    if type_name == "ScalarBoolean":
        return bool(value)
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return float(value)
    if isinstance(value, str):
        return str(value)
    return str(value)
