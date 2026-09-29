"""Text snapshots (ANSI to HTML) and console crop geometry."""

from __future__ import annotations

from scenarioplay.console.geometry import cells_to_region
from scenarioplay.report.snapshot import (
    ansi_to_html,
    color256,
    render_page,
    render_text,
    strip_ansi,
)

PROMPT = "\x1b[01;32muser@lab\x1b[00m:\x1b[01;34m~\x1b[00m$ ls\n"


def test_colours_and_bold():
    out = ansi_to_html(PROMPT)
    assert '<span style="color:#cd0000' not in out
    assert '<span style="color:#00cd00;font-weight:bold">user@lab</span>' in out
    assert '<span style="color:#0000ee;font-weight:bold">~</span>' in out
    assert out.endswith("$ ls\n")


def test_256_truecolor_reverse_and_escaping():
    assert color256(196) == "#ff0000" and color256(244) == "#808080"
    out = ansi_to_html("\x1b[38;5;196mred\x1b[0m \x1b[48;2;1;2;3mbg\x1b[0m "
                       "\x1b[7mrev\x1b[27m <a&b>")
    assert '<span style="color:#ff0000">red</span>' in out
    assert '<span style="background:#010203">bg</span>' in out
    assert '<span style="color:#000000;background:#d0d0d0">rev</span>' in out
    assert "&lt;a&amp;b&gt;" in out


def test_other_escapes_are_dropped():
    text = "\x1b]0;title\x07\x1b[2Khello\x1b[?25l"
    assert strip_ansi(text) == "hello"
    assert ansi_to_html(text) == "hello"


def test_page_and_text_render_every_console():
    blocks = [("Server", PROMPT), ("Client", "\x1b[31mERR\x1b[0m\n")]
    page = render_page("Lab - after-install", blocks)
    assert page.startswith("<!DOCTYPE html>") and "<h2>Server</h2>" in page
    assert "<title>Lab - after-install</title>" in page
    text = render_text(blocks)
    assert "=== Client ===\nERR" in text and "\x1b" not in text
    assert render_text([("only", "plain\n")]) == "plain\n"


def test_cells_to_region():
    # A pane at column 76 of a split layout, rows 1..39, cells of 11x22 px.
    assert cells_to_region(76, 1, 74, 39, 11, 22, title_row=True, status_row=False) == \
        (836, 0, 814, 880)  # the title row above the pane is included
    assert cells_to_region(0, 0, 150, 39, 11, 22, title_row=False, status_row=True) == \
        (0, 22, 1650, 858)  # tabs: below the tab bar
