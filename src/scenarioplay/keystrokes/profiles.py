"""Typing parameters (spec section 6.3): profiles and layering."""

from __future__ import annotations

import copy
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from ..loader.model import TypingSpec


@dataclass(frozen=True)
class TyposParams:
    enabled: bool
    rate: float
    kinds: dict[str, float]
    notice_after: tuple[int, int]
    hesitation: tuple[float, float]
    backspace_cps: float
    max_per_line: int
    min_length: int
    protect: tuple[str, ...]
    seed: int | None


@dataclass(frozen=True)
class BurstParams:
    chance: float
    speedup: float
    length: tuple[int, int]


@dataclass(frozen=True)
class RewordParams:
    chance: float
    hesitation: tuple[float, float]
    min_length: int


@dataclass(frozen=True)
class TypingParams:
    profile: str
    speed: float
    cps: float
    jitter: float
    word_pause: tuple[float, float]
    punctuation_pause: tuple[float, float]
    shifted_slowdown: float
    think_before: tuple[float, float]
    think_long_threshold: int
    burst: BurstParams
    reword: RewordParams
    layout: str
    typos: TyposParams


# The `normal` profile, which is also the base every other profile modifies.
BASE: dict[str, Any] = {
    "profile": "normal",
    # Overall pace multiplier applied on top of `cps`. 0.7 => 30% slower by default; a
    # scenario can set `speed` to go faster or slower without touching the profile.
    "speed": 0.7,
    "cps": 9.0,
    "jitter": 0.35,
    # Pause after a space, before the next word. A wide range makes the rhythm between
    # words clearly vary, which is what makes typing look human.
    "word_pause": (0.05, 0.5),
    "punctuation_pause": (0.1, 0.4),
    "shifted_slowdown": 1.4,
    "think_before": (0.3, 1.2),
    "think_long_threshold": 40,
    "burst": {"chance": 0.15, "speedup": 1.8, "length": (3, 8)},
    # Occasionally backspace a whole word and retype it (only on a shell command line).
    "reword": {"chance": 0.05, "hesitation": (0.3, 0.7), "min_length": 3},
    "layout": "us",
    "typos": {
        "enabled": True,
        "rate": 0.03,
        "kinds": {"neighbour": 0.6, "transposition": 0.15, "doubled": 0.1, "missed": 0.1,
                  "case": 0.05},
        "notice_after": (0, 3),
        "hesitation": (0.2, 0.6),
        "backspace_cps": 18.0,
        "max_per_line": 2,
        "min_length": 6,
        "protect": (),
        "seed": None,
    },
}

# Profiles only set speed and realism fields, never layout, protect or seed, so switching
# profile at one level keeps those from earlier levels.
PROFILES: dict[str, dict[str, Any]] = {
    "normal": {
        "cps": 9.0, "jitter": 0.35, "word_pause": (0.05, 0.5),
        "punctuation_pause": (0.1, 0.4), "shifted_slowdown": 1.4,
        "think_before": (0.3, 1.2),
        "burst": {"chance": 0.15, "speedup": 1.8},
        "reword": {"chance": 0.05},
        "typos": {"enabled": True, "rate": 0.03},
    },
    "novice": {
        "cps": 4.0, "jitter": 0.5, "word_pause": (0.1, 0.7),
        "punctuation_pause": (0.2, 0.7), "shifted_slowdown": 1.8,
        "think_before": (0.8, 2.5),
        "burst": {"chance": 0.03, "speedup": 1.3},
        "reword": {"chance": 0.09},          # a novice second-guesses words more
        "typos": {"enabled": True, "rate": 0.06, "notice_after": (1, 4)},
    },
    "expert": {
        "cps": 16.0, "jitter": 0.25, "word_pause": (0.02, 0.2),
        "punctuation_pause": (0.04, 0.15), "shifted_slowdown": 1.15,
        "think_before": (0.2, 0.6),
        "burst": {"chance": 0.3, "speedup": 2.0},
        "reword": {"chance": 0.02},          # an expert rarely rewords
        "typos": {"enabled": True, "rate": 0.01, "notice_after": (0, 1)},
    },
    "robot": {
        "speed": 1.0,                        # robot = exact, unscaled pace (no 30% slowdown)
        "cps": 25.0, "jitter": 0.0, "word_pause": (0.0, 0.0),
        "punctuation_pause": (0.0, 0.0), "shifted_slowdown": 1.0,
        "think_before": (0.0, 0.0),
        "burst": {"chance": 0.0},
        "reword": {"chance": 0.0},
        "typos": {"enabled": False},
    },
}


def _merge(into: dict[str, Any], new: dict[str, Any]) -> None:
    for key, value in new.items():
        if isinstance(value, dict) and isinstance(into.get(key), dict):
            _merge(into[key], value)
        else:
            into[key] = value


def resolve_typing(levels: Iterable[TypingSpec | None], *, typos_rate: float | None = None,
                   no_typos: bool = False) -> TypingParams:
    """Layer typing specs from least to most specific (defaults, console, step).

    At each level a `profile` is applied first, then that level's explicit fields.
    """
    d = copy.deepcopy(BASE)
    for level in levels:
        if level is None:
            continue
        raw = level.model_dump(exclude_none=True)
        profile = raw.pop("profile", None)
        if profile:
            _merge(d, copy.deepcopy(PROFILES[profile]))
            d["profile"] = profile
        _merge(d, raw)
    if typos_rate is not None:
        d["typos"]["rate"] = typos_rate
        d["typos"]["enabled"] = typos_rate > 0
    if no_typos:
        d["typos"]["enabled"] = False
    t = d["typos"]
    r = d["reword"]
    return TypingParams(
        profile=d["profile"], speed=float(d["speed"]), cps=float(d["cps"]),
        jitter=float(d["jitter"]),
        word_pause=tuple(d["word_pause"]), punctuation_pause=tuple(d["punctuation_pause"]),
        shifted_slowdown=float(d["shifted_slowdown"]), think_before=tuple(d["think_before"]),
        think_long_threshold=int(d["think_long_threshold"]),
        burst=BurstParams(float(d["burst"]["chance"]), float(d["burst"]["speedup"]),
                          tuple(d["burst"]["length"])),
        reword=RewordParams(float(r["chance"]), tuple(r["hesitation"]), int(r["min_length"])),
        layout=str(d["layout"]),
        typos=TyposParams(
            enabled=bool(t["enabled"]), rate=float(t["rate"]), kinds=dict(t["kinds"]),
            notice_after=tuple(t["notice_after"]), hesitation=tuple(t["hesitation"]),
            backspace_cps=float(t["backspace_cps"]), max_per_line=int(t["max_per_line"]),
            min_length=int(t["min_length"]), protect=tuple(t["protect"]), seed=t["seed"]),
    )  # type: ignore[arg-type]
