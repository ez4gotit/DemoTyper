"""Keystroke planning (spec section 6.1). Pure functions: text + parameters + rng -> events.

Auto-typos (section 6.2) plug in here in phase 4; the Backspace event kind already exists so
the executor and the tests do not change then.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Literal

from .profiles import TypingParams

# Characters typed with Shift on the US layout (layout files arrive with auto-typos).
US_SHIFTED = set('~!@#$%^&*()_+{}|:"<>?')
PUNCTUATION = set(".,;:!?")


@dataclass(frozen=True)
class Keystroke:
    kind: Literal["char", "backspace"]
    value: str
    delay: float  # seconds to wait before sending this keystroke


def is_shifted(ch: str) -> bool:
    return ch.isupper() or ch in US_SHIFTED


def think_time(text: str, p: TypingParams, rng: random.Random, speed: float = 1.0) -> float:
    """Pause before starting to type a command."""
    lo, hi = p.think_before
    t = rng.uniform(lo, hi)
    if len(text) > p.think_long_threshold:
        t *= 1.6
    return t / speed


def plan_typing(text: str, p: TypingParams, rng: random.Random,
                speed: float = 1.0) -> list[Keystroke]:
    """Plan the keystrokes for one line of text (no newlines)."""
    if "\n" in text:
        raise ValueError("plan_typing takes one line; split on newlines first")
    base = 1.0 / p.cps
    events: list[Keystroke] = []
    prev: str | None = None
    burst_left = 0
    for ch in text:
        delay = base * max(0.25, rng.gauss(1.0, p.jitter)) if p.jitter > 0 else base
        if is_shifted(ch):
            delay *= p.shifted_slowdown
        if prev == " ":
            delay += rng.uniform(*p.word_pause)
        elif prev is not None and prev in PUNCTUATION:
            delay += rng.uniform(*p.punctuation_pause)
        if burst_left == 0 and prev in (None, " ") and p.burst.chance > 0 \
                and rng.random() < p.burst.chance:
            burst_left = rng.randint(*p.burst.length)
        if burst_left > 0:
            delay /= p.burst.speedup
            burst_left -= 1
        events.append(Keystroke("char", ch, delay / speed))
        prev = ch
    return events


def replay(events: list[Keystroke]) -> str:
    """What the input line holds after the events (used by tests and the dry run)."""
    buf: list[str] = []
    for ev in events:
        if ev.kind == "char":
            buf.append(ev.value)
        elif buf:
            buf.pop()
    return "".join(buf)
