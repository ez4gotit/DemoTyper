"""{{ }} templates (spec 5.1): text with expressions inside double braces."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from .expr import Env, ExprError, Node, parse_expression, to_text

_OPEN = "{{"
_CLOSE = "}}"


@dataclass(frozen=True)
class Template:
    parts: tuple[str | Node, ...]

    @property
    def is_static(self) -> bool:
        return all(isinstance(p, str) for p in self.parts)

    @property
    def single(self) -> Node | None:
        """The expression, when the whole text is one {{ expr }} (renders a native value)."""
        if len(self.parts) == 1 and not isinstance(self.parts[0], str):
            return self.parts[0]
        return None

    def names(self) -> set[str]:
        out: set[str] = set()
        for p in self.parts:
            if not isinstance(p, str):
                out |= p.names()
        return out

    def paths(self) -> set[str]:
        out: set[str] = set()
        for p in self.parts:
            if not isinstance(p, str):
                out |= p.paths()
        return out

    def render(self, env: Env, *, native: bool = False) -> Any:
        """Render to text. With native=True, a single {{ expr }} keeps its type (a list
        stays a list), which `for_each: "{{ packages }}"` needs."""
        single = self.single
        if native and single is not None:
            value = single.eval(env)
            to_text(value)  # raises for undefined values
            return value
        out = []
        for p in self.parts:
            out.append(p if isinstance(p, str) else to_text(p.eval(env)))
        return "".join(out)


@lru_cache(maxsize=4096)
def parse_template(text: str) -> Template:
    parts: list[str | Node] = []
    pos = 0
    while True:
        start = text.find(_OPEN, pos)
        if start < 0:
            if pos < len(text):
                parts.append(text[pos:])
            break
        end = text.find(_CLOSE, start + 2)
        if end < 0:
            raise ExprError("'{{' without a closing '}}'", start)
        if start > pos:
            parts.append(text[pos:start])
        body = text[start + 2:end]
        try:
            parts.append(parse_expression(body))
        except ExprError as e:
            raise ExprError(f"in {{{{{body}}}}}: {e}", start) from None
        pos = end + 2
    # Only a text that is exactly one {{ expr }} renders natively; "x {{ y }}" is text.
    return Template(tuple(parts))


def has_template(text: str) -> bool:
    return _OPEN in text
