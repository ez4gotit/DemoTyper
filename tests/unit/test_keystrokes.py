from __future__ import annotations

import random

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from scenarioplay.keystrokes import plan_typing, resolve_typing, think_time
from scenarioplay.keystrokes.planner import plan_line, replay
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
    p = resolve_typing([TypingSpec(cps=10, speed=1.0, burst={"chance": 0}, word_pause=(0, 0),
                                   punctuation_pause=(0, 0), shifted_slowdown=1)])
    events = plan_typing("abcdefghij" * 200, p, random.Random(7))
    mean = sum(ev.delay for ev in events) / len(events)
    assert mean == pytest.approx(0.1, rel=0.08)


def test_default_speed_is_30_percent_slower():
    """The default `speed` is 0.7, i.e. 30% slower than the raw profile pace."""
    fast = resolve_typing([TypingSpec(profile="normal", jitter=0, word_pause=(0, 0),
                                      burst={"chance": 0}, speed=1.0)])
    default = resolve_typing([TypingSpec(profile="normal", jitter=0, word_pause=(0, 0),
                                         burst={"chance": 0})])
    assert default.speed == 0.7
    a = plan_typing("abcdef", fast, random.Random(1))
    b = plan_typing("abcdef", default, random.Random(1))
    # every delay is 1/0.7 longer at the default pace
    assert [x.delay / 0.7 for x in a] == pytest.approx([y.delay for y in b])


def test_speed_parameter_scales_pace():
    p = resolve_typing([TypingSpec(profile="robot", speed=2.0)])
    events = plan_typing("hello", p, random.Random(1))
    # robot base is 1/25 s; speed 2 halves it
    assert events[0].delay == pytest.approx(1 / 25 / 2)


def test_robot_keeps_exact_pace_by_default():
    p = resolve_typing([TypingSpec(profile="robot")])
    assert p.speed == 1.0            # robot opts out of the 30% slowdown
    events = plan_typing("a b c", p, random.Random(1))
    assert {round(e.delay, 9) for e in events} == {round(1 / p.cps, 9)}


def test_reword_backspaces_and_retypes_a_word():
    p = resolve_typing([TypingSpec(profile="normal", reword={"chance": 1.0, "min_length": 3},
                                   typos={"enabled": False})])
    plan = plan_line("install nginx", p, random.Random(1), typos=True)
    assert plan.rewords  # at least one word reworded
    assert replay(plan.events) == "install nginx"       # net text is unchanged
    assert any(e.kind == "backspace" for e in plan.events)


def test_reword_is_off_when_backspacing_is_unsafe():
    p = resolve_typing([TypingSpec(profile="normal", reword={"chance": 1.0})])
    plan = plan_line("install nginx", p, random.Random(1), typos=False)  # e.g. inside nano
    assert plan.rewords == [] and not any(e.kind == "backspace" for e in plan.events)


def test_new_word_has_more_pace_variation():
    """The first keystroke after a space varies more than a mid-word keystroke."""
    from statistics import pstdev
    p = resolve_typing([TypingSpec(profile="normal", word_pause=(0, 0), speed=1.0,
                                   typos={"enabled": False})])
    after_space, mid_word = [], []
    for seed in range(400):
        ev = plan_typing("aa aa", p, random.Random(seed))  # index 3 is after the space
        mid_word.append(ev[1].delay)      # second 'a', mid-word
        after_space.append(ev[3].delay)   # first 'a' of the second word
    assert pstdev(after_space) > pstdev(mid_word)


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
