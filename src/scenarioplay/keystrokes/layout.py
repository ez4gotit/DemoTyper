"""Keyboard layouts for realistic typos (spec 6.2): which keys are next to each other, and
which characters need Shift."""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from pathlib import Path

from ruamel.yaml import YAML

BUILTIN = ("us", "de", "ru")
NEIGHBOUR_DISTANCE = 1.3  # in key widths: the keys around a key, diagonals included


@dataclass(frozen=True)
class Layout:
    name: str
    positions: dict[str, tuple[float, float, bool]]  # char -> (x, row, shifted)
    counterpart: dict[str, str]  # char <-> the same key on the other (Shift) layer

    def is_shifted(self, ch: str) -> bool:
        pos = self.positions.get(ch)
        if pos is not None:
            return pos[2]
        return ch.isupper()

    def neighbours(self, ch: str) -> list[str]:
        """Characters on keys next to this one, on the same Shift layer."""
        pos = self.positions.get(ch)
        if pos is None:
            return []
        x, row, shifted = pos
        out = []
        for other, (ox, orow, oshift) in self.positions.items():
            if other == ch or oshift != shifted:
                continue
            if math.hypot(ox - x, orow - row) <= NEIGHBOUR_DISTANCE:
                out.append(other)
        return sorted(out)

    def wrong_case(self, ch: str) -> str | None:
        """What Shift held too long or released too early gives: 'n' -> 'N', '1' -> '!'."""
        if ch.isalpha() and ch.swapcase() != ch:
            return ch.swapcase()
        return self.counterpart.get(ch)


def parse_layout(data: dict, name: str) -> Layout:
    rows = data.get("rows") or []
    shift = data.get("shift") or []
    offsets = data.get("offsets") or [0.0] * len(rows)
    if not rows or len(shift) not in (0, len(rows)) or len(offsets) < len(rows):
        raise ValueError(f"layout {name}: needs `rows`, and `shift`/`offsets` of the same length")
    positions: dict[str, tuple[float, float, bool]] = {}
    counterpart: dict[str, str] = {}
    for r, line in enumerate(rows):
        for c, ch in enumerate(line):
            positions.setdefault(ch, (c + float(offsets[r]), float(r), False))
    for r, line in enumerate(shift):
        for c, ch in enumerate(line):
            positions.setdefault(ch, (c + float(offsets[r]), float(r), True))
            if c < len(rows[r]):
                base = rows[r][c]
                counterpart.setdefault(ch, base)
                counterpart.setdefault(base, ch)
    return Layout(data.get("name", name), positions, counterpart)


@lru_cache(maxsize=16)
def load_layout(name_or_path: str) -> Layout:
    """A built-in layout (us, de, ru) or a YAML file in the same format."""
    yaml = YAML(typ="safe")
    if name_or_path in BUILTIN:
        text = (files("scenarioplay.keystrokes") / "layouts" / f"{name_or_path}.yaml").read_text(
            encoding="utf-8")
    else:
        path = Path(name_or_path).expanduser()
        if not path.exists():
            raise ValueError(f"unknown keyboard layout {name_or_path!r} (built in: "
                             f"{', '.join(BUILTIN)}, or a path to a layout YAML file)")
        text = path.read_text(encoding="utf-8")
    return parse_layout(yaml.load(text), name_or_path)
