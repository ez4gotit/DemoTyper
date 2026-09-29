"""Keystroke planning (spec 6.1-6.3). Pure functions: text + parameters + rng -> events.

With typos on, the plan sometimes types a wrong character (or skips, doubles or swaps
one), keeps typing for a few characters, "notices", pauses, backspaces over everything since
the mistake and retypes it. Whatever happens, replaying the events gives exactly the text.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Literal

from .layout import Layout, load_layout
from .profiles import TypingParams

PUNCTUATION = set(".,;:!?")


@dataclass(frozen=True)
class Keystroke:
    kind: Literal["char", "backspace"]
    value: str
    delay: float  # seconds to wait before sending this keystroke


@dataclass(frozen=True)
class Typo:
    """One mistake and its correction, for the take log (spec 6.3)."""

    position: int  # index in the text of the first wrong character
    kind: str
    intended: str  # the correct text at that position
    typed: str  # what was typed instead
    noticed_after: int  # correct characters typed before noticing

    def describe(self) -> str:
        return (f"typo at {self.position} ({self.kind}): {self.intended!r} typed as "
                f"{self.typed!r}, noticed after {self.noticed_after} more, corrected")


@dataclass
class Plan:
    events: list[Keystroke] = field(default_factory=list)
    typos: list[Typo] = field(default_factory=list)


def think_time(text: str, p: TypingParams, rng: random.Random, speed: float = 1.0) -> float:
    """Pause before starting to type a command."""
    lo, hi = p.think_before
    t = rng.uniform(lo, hi)
    if len(text) > p.think_long_threshold:
        t *= 1.6
    return t / speed


class _Typist:
    """Keeps timing state (previous char, burst) while a plan is built."""

    def __init__(self, p: TypingParams, rng: random.Random, speed: float, layout: Layout):
        self.p, self.rng, self.speed, self.layout = p, rng, speed, layout
        self.prev: str | None = None
        self.burst_left = 0
        self.events: list[Keystroke] = []

    def char(self, ch: str, extra: float = 0.0) -> None:
        p, rng = self.p, self.rng
        delay = (1.0 / p.cps) * max(0.25, rng.gauss(1.0, p.jitter)) if p.jitter > 0 \
            else 1.0 / p.cps
        if self.layout.is_shifted(ch):
            delay *= p.shifted_slowdown
        if self.prev == " ":
            delay += rng.uniform(*p.word_pause)
        elif self.prev is not None and self.prev in PUNCTUATION:
            delay += rng.uniform(*p.punctuation_pause)
        if self.burst_left == 0 and self.prev in (None, " ") and p.burst.chance > 0 \
                and rng.random() < p.burst.chance:
            self.burst_left = rng.randint(*p.burst.length)
        if self.burst_left > 0:
            delay /= p.burst.speedup
            self.burst_left -= 1
        self.events.append(Keystroke("char", ch, (delay + extra) / self.speed))
        self.prev = ch

    def backspaces(self, count: int, hesitation: float) -> None:
        base = 1.0 / self.p.typos.backspace_cps
        for i in range(count):
            delay = base * max(0.5, self.rng.gauss(1.0, 0.2))
            if i == 0:
                delay += hesitation
            self.events.append(Keystroke("backspace", "", delay / self.speed))
        self.burst_left = 0


def _typo_options(text: str, i: int, layout: Layout, protect: set[str]
                  ) -> dict[str, tuple[str, int]]:
    """Possible typos at position i: kind -> (what gets typed, how many chars it covers)."""
    ch = text[i]
    options: dict[str, tuple[str, int]] = {}
    neighbours = [n for n in layout.neighbours(ch) if n not in protect]
    if neighbours:
        options["neighbour"] = ("", 1)  # the neighbour is picked later with the rng
    nxt = text[i + 1] if i + 1 < len(text) else None
    if nxt is not None and nxt != ch and nxt not in protect and nxt != " ":
        options["transposition"] = (nxt + ch, 2)
    options["doubled"] = (ch + ch, 1)
    if i + 1 < len(text):  # a key missed at the very end would be noticed at once
        options["missed"] = ("", 1)
    swapped = layout.wrong_case(ch)
    if swapped and swapped not in protect:
        options["case"] = (swapped, 1)
    return options


def plan_line(text: str, p: TypingParams, rng: random.Random, speed: float = 1.0, *,
              typos: bool = False) -> Plan:
    """Plan the keystrokes for one line of text (no newlines)."""
    if "\n" in text:
        raise ValueError("plan_line takes one line; split on newlines first")
    layout = load_layout(p.layout)
    t = _Typist(p, rng, speed, layout)
    plan = Plan()
    tp = p.typos
    allowed = typos and tp.enabled and tp.rate > 0 and len(text) >= tp.min_length
    protect = set(tp.protect)
    budget = tp.max_per_line
    i = 0
    while i < len(text):
        ch = text[i]
        if (allowed and budget > 0 and ch != " " and ch not in protect
                and rng.random() < tp.rate):
            options = _typo_options(text, i, layout, protect)
            weights = [tp.kinds.get(k, 0.0) for k in options]
            if options and sum(weights) > 0:
                kind = rng.choices(list(options), weights=weights)[0]
                typed, covers = options[kind]
                if kind == "neighbour":
                    typed = rng.choice([n for n in layout.neighbours(ch) if n not in protect])
                elif kind == "missed":
                    typed = ""
                # Keep typing correctly for a few characters before noticing.
                lo, hi = tp.notice_after
                if kind == "missed":
                    lo, hi = max(lo, 1), max(hi, 1)  # a gap only shows once past it
                after = min(rng.randint(lo, hi), len(text) - (i + covers))
                following = text[i + covers:i + covers + after]
                for c in typed + following:
                    t.char(c)
                t.backspaces(len(typed) + len(following), rng.uniform(*tp.hesitation))
                for c in text[i:i + covers + after]:
                    t.char(c)
                plan.typos.append(Typo(i, kind, text[i:i + covers], typed, after))
                budget -= 1
                i += covers + after
                continue
        t.char(ch)
        i += 1
    plan.events = t.events
    return plan


def plan_typing(text: str, p: TypingParams, rng: random.Random, speed: float = 1.0, *,
                typos: bool = False) -> list[Keystroke]:
    return plan_line(text, p, rng, speed, typos=typos).events


def is_shifted(ch: str, layout: str = "us") -> bool:
    return load_layout(layout).is_shifted(ch)


def replay(events: list[Keystroke]) -> str:
    """What the input line holds after the events (used by tests and the dry run)."""
    buf: list[str] = []
    for ev in events:
        if ev.kind == "char":
            buf.append(ev.value)
        elif buf:
            buf.pop()
    return "".join(buf)
