from __future__ import annotations

import random

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from scenarioplay.keystrokes import plan_typing, resolve_typing, think_time
from scenarioplay.keystrokes.planner import replay
from scenarioplay.loader.model import TypingSpec

line_text = st.text(
    alphabet=st.characters(blacklist_categories=("Cc", "Cs"), blacklist_characters="\n"),
    max_size=120)


@settings(max_examples=300)
@given(text=line_text, seed=st.integers(), profile=st.sampled_from(
    ["novice", "normal", "expert", "robot"]))
def test_replaying_the_plan_gives_the_text(text, seed, profile):
    params = resolve_typing([TypingSpec(profile=profile)])
    events = plan_typing(text, params, random.Random(seed))
    assert replay(events) == text
    assert all(ev.delay >= 0 for ev in events)


def test_same_seed_same_plan():
    p = resolve_typing([None])
    a = plan_typing("sudo apt install -y nginx", p, random.Random("s"))
    b = plan_typing("sudo apt install -y nginx", p, random.Random("s"))
    assert a == b


def test_robot_is_constant_speed():
    p = resolve_typing([TypingSpec(profile="robot")])
    events = plan_typing("Hello, World! ls -la", p, random.Random(1))
    assert {round(ev.delay, 9) for ev in events} == {round(1 / p.cps, 9)}
    assert think_time("x", p, random.Random(1)) == 0


def test_mean_speed_close_to_cps():
    p = resolve_typing([TypingSpec(cps=10, burst={"chance": 0}, word_pause=(0, 0),
                                   punctuation_pause=(0, 0), shifted_slowdown=1)])
    events = plan_typing("abcdefghij" * 200, p, random.Random(7))
    mean = sum(ev.delay for ev in events) / len(events)
    assert mean == pytest.approx(0.1, rel=0.08)


def test_speed_scales_delays():
    p = resolve_typing([TypingSpec(profile="robot")])
    slow = plan_typing("abc", p, random.Random(1), speed=1)
    fast = plan_typing("abc", p, random.Random(1), speed=2)
    assert [f.delay * 2 for f in fast] == pytest.approx([s.delay for s in slow])


def test_shifted_chars_are_slower():
    p = resolve_typing([TypingSpec(profile="robot", shifted_slowdown=2.0)])
    events = plan_typing("a{", p, random.Random(1))
    assert events[1].delay == pytest.approx(2 * events[0].delay)


def test_word_pause_after_space():
    p = resolve_typing([TypingSpec(profile="robot", word_pause=(0.5, 0.5))])
    events = plan_typing("a b", p, random.Random(1))
    assert events[2].delay == pytest.approx(events[0].delay + 0.5)


def test_profile_layering_keeps_layout_and_seed():
    defaults = TypingSpec(profile="normal", layout="de", typos={"seed": 42})
    step = TypingSpec(profile="expert")
    p = resolve_typing([defaults, None, step])
    assert p.profile == "expert" and p.cps == 16
    assert p.layout == "de" and p.typos.seed == 42


def test_explicit_fields_override_profile_at_same_level():
    p = resolve_typing([TypingSpec(profile="expert", cps=5)])
    assert p.cps == 5


def test_cli_typo_overrides():
    assert resolve_typing([None], typos_rate=0.1).typos.rate == 0.1
    assert not resolve_typing([None], no_typos=True).typos.enabled
    assert not resolve_typing([TypingSpec(profile="robot")]).typos.enabled


def test_newline_rejected():
    with pytest.raises(ValueError):
        plan_typing("a\nb", resolve_typing([None]), random.Random())
