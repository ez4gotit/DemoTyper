"""Auto-typos (spec 6.2): layouts, typo kinds, budget, protection, reproducibility."""

from __future__ import annotations

import random
from collections import Counter

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from scenarioplay.keystrokes import plan_line, resolve_typing
from scenarioplay.keystrokes.layout import load_layout, parse_layout
from scenarioplay.keystrokes.planner import replay
from scenarioplay.loader.model import TypingSpec


def params(**typos):
    spec = {"enabled": True, "rate": 0.3, "min_length": 0, "max_per_line": 100, **typos}
    return resolve_typing([TypingSpec(profile="expert", typos=spec)])


def test_us_neighbours_and_shift_layer():
    us = load_layout("us")
    assert set(us.neighbours("g")) >= {"f", "h", "t", "y", "v", "b"}
    assert "q" not in us.neighbours("g")
    assert set(us.neighbours("!")) >= {"~", "@", "Q"}  # the Shift layer: `!` next to `@`
    assert us.wrong_case("n") == "N" and us.wrong_case("1") == "!" and us.wrong_case("?") == "/"
    assert us.is_shifted("{") and not us.is_shifted("[")


def test_de_and_ru_layouts():
    de = load_layout("de")
    assert "t" in de.neighbours("z") and "u" in de.neighbours("z")  # QWERTZ
    ru = load_layout("ru")
    assert "ц" in ru.neighbours("у") and "к" in ru.neighbours("у")
    assert ru.neighbours("n") == []  # Latin is not on the Russian layout


def test_custom_layout_file(tmp_path):
    f = tmp_path / "mini.yaml"
    f.write_text('name: mini\nrows: ["abc", "def"]\nshift: ["ABC", "DEF"]\noffsets: [0, 0]\n')
    layout = load_layout(str(f))
    # No stagger: diagonals are 1.41 key widths away, beyond the neighbour distance.
    assert set(layout.neighbours("b")) == {"a", "c", "e"}
    with pytest.raises(ValueError, match="unknown keyboard layout"):
        load_layout("dvorak-nope")
    with pytest.raises(ValueError):
        parse_layout({"rows": ["ab"], "shift": ["AB", "CD"]}, "bad")


@settings(max_examples=400)
@given(text=st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789 -./|{}$'\"ЮникодÄß",
                    max_size=80),
       seed=st.integers(), layout=st.sampled_from(["us", "de", "ru"]))
def test_every_plan_replays_to_the_text(text, seed, layout):
    p = resolve_typing([TypingSpec(profile="novice", layout=layout,
                                   typos={"rate": 0.5, "min_length": 0, "max_per_line": 50})])
    plan = plan_line(text, p, random.Random(seed), typos=True)
    assert replay(plan.events) == text
    assert all(ev.delay >= 0 for ev in plan.events)


def test_all_kinds_happen_and_are_logged():
    text = "sudo systemctl restart nginx && curl -sI http://localhost"
    kinds = Counter()
    for seed in range(300):
        plan = plan_line(text, params(rate=0.2), random.Random(seed), typos=True)
        for typo in plan.typos:
            kinds[typo.kind] += 1
            assert text[typo.position:typo.position + len(typo.intended)] == typo.intended
            assert typo.typed != typo.intended
    assert set(kinds) == {"neighbour", "transposition", "doubled", "missed", "case"}
    assert kinds["neighbour"] > kinds["case"]  # default weights: 0.6 vs 0.05


def test_correction_shape():
    """A typo shows the wrong text, a hesitation, fast backspaces, then the right text."""
    p = params(rate=1.0, max_per_line=1, notice_after=(2, 2), hesitation=(0.5, 0.5),
               kinds={"neighbour": 1.0}, backspace_cps=20)
    plan = plan_line("nginx -t", p, random.Random(3), typos=True)
    (typo,) = plan.typos
    kinds = [ev.kind for ev in plan.events]
    first_bs = kinds.index("backspace")
    assert kinds.count("backspace") == 3  # the wrong key + the 2 typed after it
    assert plan.events[first_bs].delay >= 0.5  # "noticed it"
    assert plan.events[first_bs + 1].delay < 0.1  # backspace is fast
    assert typo.noticed_after == 2


def test_budget_min_length_protect_and_disabled():
    text = "cat /etc/hosts | grep localhost"
    p = params(rate=1.0, max_per_line=2)
    assert len(plan_line(text, p, random.Random(1), typos=True).typos) == 2
    assert plan_line("ls -la", params(rate=1.0, min_length=10),
                     random.Random(1), typos=True).typos == []
    protected = plan_line(text, params(rate=1.0, protect=list(set(text) - {" "})),
                          random.Random(1), typos=True)
    assert protected.typos == []
    assert plan_line(text, p, random.Random(1), typos=False).typos == []
    assert plan_line(text, params(rate=1.0, enabled=False),
                     random.Random(1), typos=True).typos == []


def test_seed_reproduces_typos():
    p = params(rate=0.1)
    a = plan_line("docker compose up -d --build", p, random.Random("7:steps.3"), typos=True)
    b = plan_line("docker compose up -d --build", p, random.Random("7:steps.3"), typos=True)
    assert a.events == b.events and a.typos == b.typos
