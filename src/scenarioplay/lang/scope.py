"""Variable scopes (spec 5.1).

Lookup order, innermost first: loop / call / catch scopes, runtime values (`set`,
`capture`), --vars file, --var, file `vars`, built-ins (env, secret, take, last).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from typing import Any

from .expr import Env, Undefined


class LiveMapping(Mapping[str, Any]):
    """A mapping whose values are read when used (for `last`)."""

    def __init__(self, read: Callable[[], dict[str, Any]]):
        self._read = read

    def __getitem__(self, key: str) -> Any:
        return self._read()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._read())

    def __len__(self) -> int:
        return len(self._read())


class Scope(Env):
    def __init__(self, builtins: dict[str, Any], globals_: list[dict[str, Any]]):
        self.builtins = builtins
        # Global layers, lowest priority first: file vars, --var, --vars, runtime.
        self.globals = globals_
        self.runtime = globals_[-1]
        self.locals: list[dict[str, Any]] = []

    def lookup(self, name: str) -> Any:
        for layer in reversed(self.locals):
            if name in layer:
                return layer[name]
        for layer in reversed(self.globals):
            if name in layer:
                return layer[name]
        if name in self.builtins:
            return self.builtins[name]
        return Undefined(name)

    def push(self, values: dict[str, Any]) -> None:
        self.locals.append(values)

    def pop(self) -> None:
        self.locals.pop()

    def set(self, name: str, value: Any) -> None:
        """`set`/`capture`: update the innermost local that has the name, else the
        runtime layer (so values set inside a loop stay visible after it)."""
        for layer in reversed(self.locals):
            if name in layer:
                layer[name] = value
                return
        self.runtime[name] = value

    def snapshot(self) -> dict[str, Any]:
        """Effective global variables (for the resolved scenario and the report)."""
        out: dict[str, Any] = {}
        for layer in self.globals:
            out.update(layer)
        return out
