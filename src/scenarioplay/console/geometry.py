"""Where a console is on the screen, in pixels (for screenshots of one console).

tmux knows each pane's position in cells and, from the attached terminal, the size of a
cell in pixels (`client_cell_width/height`, tmux 3.3+). The terminal window is assumed to
start at the screen's top-left corner, which holds for a full-screen terminal.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .driver import Console
    from .session import Session

Region = tuple[int, int, int, int]  # x, y, width, height

_FORMAT = ("#{pane_left} #{pane_top} #{pane_width} #{pane_height} "
           "#{client_cell_width} #{client_cell_height}")


def cells_to_region(left: int, top: int, width: int, height: int, cell_w: int, cell_h: int,
                    *, title_row: bool, status_row: bool) -> Region:
    if title_row:  # split layouts: include the console's title on the border above
        top, height = top - 1, height + 1
    if status_row:  # tabs: the tab bar is the first screen row
        top += 1
    top = max(0, top)
    return left * cell_w, top * cell_h, width * cell_w, height * cell_h


async def pane_region(console: Console, session: Session) -> Region | None:
    out = await console.tmux("display-message", "-p", "-t", console.pane, _FORMAT, check=False)
    parts = out.split()
    if len(parts) != 6 or not all(p.isdigit() for p in parts):
        return None  # no terminal attached, or a tmux without cell sizes
    left, top, width, height, cell_w, cell_h = (int(p) for p in parts)
    if cell_w <= 0 or cell_h <= 0:
        return None
    return cells_to_region(left, top, width, height, cell_w, cell_h,
                           title_row=not session.windowed,
                           status_row=session.layout == "tabs")
