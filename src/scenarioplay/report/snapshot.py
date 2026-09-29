"""Text snapshots of consoles: the screen's text with its colours as a self-contained HTML
page, plus plain text. Input is what `tmux capture-pane -e` prints (ANSI SGR escapes)."""

from __future__ import annotations

import html
import re

_SGR = re.compile(r"\x1b\[([0-9;:]*)m")
_OTHER_ESCAPES = re.compile(r"\x1b(\[[0-9;?]*[A-Za-ln-z]|\][^\x07\x1b]*(\x07|\x1b\\)|[()][0-9A-B])")

# xterm's default 16 colours.
BASE16 = ["#000000", "#cd0000", "#00cd00", "#cdcd00", "#0000ee", "#cd00cd", "#00cdcd",
          "#e5e5e5", "#7f7f7f", "#ff0000", "#00ff00", "#ffff00", "#5c5cff", "#ff00ff",
          "#00ffff", "#ffffff"]
FOREGROUND, BACKGROUND = "#d0d0d0", "#000000"


def color256(n: int) -> str:
    if n < 16:
        return BASE16[n]
    if n < 232:
        n -= 16
        steps = [0, 95, 135, 175, 215, 255]
        r, g, b = steps[n // 36], steps[n // 6 % 6], steps[n % 6]
        return f"#{r:02x}{g:02x}{b:02x}"
    level = 8 + (n - 232) * 10
    return f"#{level:02x}{level:02x}{level:02x}"


def strip_ansi(text: str) -> str:
    return _OTHER_ESCAPES.sub("", _SGR.sub("", text))


class _Style:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.fg: str | None = None
        self.bg: str | None = None
        self.bold = self.dim = self.italic = self.underline = self.reverse = False

    def apply(self, params: str) -> None:
        codes = [int(p) if p.isdigit() else 0 for p in re.split(r"[;:]", params or "0")]
        i = 0
        while i < len(codes):
            c = codes[i]
            if c == 0:
                self.reset()
            elif c == 1:
                self.bold = True
            elif c == 2:
                self.dim = True
            elif c == 3:
                self.italic = True
            elif c == 4:
                self.underline = True
            elif c == 7:
                self.reverse = True
            elif c == 22:
                self.bold = self.dim = False
            elif c == 23:
                self.italic = False
            elif c == 24:
                self.underline = False
            elif c == 27:
                self.reverse = False
            elif 30 <= c <= 37:
                self.fg = BASE16[c - 30]
            elif 90 <= c <= 97:
                self.fg = BASE16[c - 90 + 8]
            elif 40 <= c <= 47:
                self.bg = BASE16[c - 40]
            elif 100 <= c <= 107:
                self.bg = BASE16[c - 100 + 8]
            elif c == 39:
                self.fg = None
            elif c == 49:
                self.bg = None
            elif c in (38, 48) and i + 1 < len(codes):
                target = "fg" if c == 38 else "bg"
                if codes[i + 1] == 5 and i + 2 < len(codes):
                    setattr(self, target, color256(codes[i + 2]))
                    i += 2
                elif codes[i + 1] == 2 and i + 4 < len(codes):
                    r, g, b = codes[i + 2:i + 5]
                    setattr(self, target, f"#{r:02x}{g:02x}{b:02x}")
                    i += 4
            i += 1

    def css(self) -> str:
        fg, bg = self.fg, self.bg
        if self.reverse:
            fg, bg = bg or BACKGROUND, fg or FOREGROUND
        parts = []
        if fg:
            parts.append(f"color:{fg}")
        if bg:
            parts.append(f"background:{bg}")
        if self.bold:
            parts.append("font-weight:bold")
        if self.dim:
            parts.append("opacity:.7")
        if self.italic:
            parts.append("font-style:italic")
        if self.underline:
            parts.append("text-decoration:underline")
        return ";".join(parts)


def ansi_to_html(text: str) -> str:
    """ANSI-coloured text to HTML spans (escaped; newlines kept for a <pre>)."""
    text = _OTHER_ESCAPES.sub("", text)
    style = _Style()
    out: list[str] = []
    pos = 0
    for m in _SGR.finditer(text):
        _emit(out, text[pos:m.start()], style)
        style.apply(m.group(1))
        pos = m.end()
    _emit(out, text[pos:], style)
    return "".join(out)


def _emit(out: list[str], chunk: str, style: _Style) -> None:
    if not chunk:
        return
    css = style.css()
    escaped = html.escape(chunk)
    out.append(f'<span style="{css}">{escaped}</span>' if css else escaped)


PAGE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>{title}</title>
<style>
body {{ background:#1b1b1b; color:{fg}; font-family: sans-serif; margin: 16px; }}
h1 {{ font-size: 16px; font-weight: normal; color:#aaa; }}
h2 {{ font-size: 14px; margin: 18px 0 6px; color:#ffaf00; }}
pre {{ background:{bg}; color:{fg}; padding: 10px 12px; margin: 0; overflow-x: auto;
      font: 14px/1.35 "DejaVu Sans Mono", Menlo, Consolas, monospace; }}
</style></head><body>
<h1>{title}</h1>
{sections}
</body></html>
"""


def render_page(title: str, consoles: list[tuple[str, str]]) -> str:
    """One HTML page with a block per console: (console title, ANSI text)."""
    sections = []
    for name, text in consoles:
        body = ansi_to_html(text.rstrip("\n"))
        heading = f"<h2>{html.escape(name)}</h2>\n" if len(consoles) > 1 else ""
        sections.append(f"{heading}<pre>{body}</pre>")
    return PAGE.format(title=html.escape(title), fg=FOREGROUND, bg=BACKGROUND,
                       sections="\n".join(sections))


def render_text(consoles: list[tuple[str, str]]) -> str:
    parts = []
    for name, text in consoles:
        body = strip_ansi(text).rstrip("\n")
        parts.append(f"=== {name} ===\n{body}" if len(consoles) > 1 else body)
    return "\n\n".join(parts) + "\n"
