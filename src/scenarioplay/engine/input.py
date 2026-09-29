"""Sending input to a console: typing, verifying the command line, pressing keys."""

from __future__ import annotations

import asyncio
import random
from typing import TYPE_CHECKING

from ..errors import StepFailed
from ..keystrokes import Keystroke, plan_line, plan_typing, resolve_typing, think_time
from ..keystrokes.profiles import TypingParams
from ..loader.model import TypingSpec
from .context import FAST

if TYPE_CHECKING:
    from ..actions.base import TypingStep
    from ..console import Console
    from .context import RunContext

VERIFY_TIMEOUT = 1.5


async def wait_hidden_input(ctx: RunContext, console: Console, timeout: float) -> None:
    """Wait until the console reads a line without echo (a password prompt). Secrets are
    never typed into a terminal that would show them."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        hidden = await console.input_hidden()
        if hidden:
            return
        if hidden is None:
            raise StepFailed("cannot read the terminal's modes (stty), so it is unknown "
                             "whether the secret would be shown; not typing it")
        if loop.time() >= deadline:
            raise StepFailed(f"no hidden-input prompt within {timeout:g}s: the terminal still "
                             "echoes what is typed, so the secret was not typed",
                             expected="a password prompt (input without echo)",
                             console=console.name)
        await asyncio.sleep(0.1)


async def send_keystrokes(console: Console, events: list[Keystroke]) -> None:
    """Send keystrokes on a deadline schedule: time spent in tmux calls is absorbed into the
    next delay instead of adding to it. When we fall behind, we do not rush to catch up."""
    loop = asyncio.get_running_loop()
    t = loop.time()
    for ev in events:
        t += ev.delay
        wait = t - loop.time()
        if wait > 0:
            await asyncio.sleep(wait)
        else:
            t = loop.time()
        if ev.kind == "char":
            await console.send_char(ev.value)
        else:
            await console.send_key("BSpace")


async def _mark_input(console: Console) -> None:
    """Remember the hook's sequence number before input, so the prompt counts as back only
    once the shell finishes something after it."""
    status = await console.status()
    if status is not None:
        console.enter_seq = status.seq


def typos_gate(ctx: RunContext, params: TypingParams, typos_off: bool, at_shell: bool,
               why_not: str) -> bool:
    """Spec 6.2: typos only on a shell command line whose text is read back and checked
    before Enter. Everywhere else they are off, whatever the scenario says."""
    if not params.typos.enabled or params.typos.rate <= 0 or typos_off:
        return False
    if not at_shell:
        ctx.log("debug", f"typos auto-off: {why_not}")
        if ctx.record is not None:
            ctx.record.notes.append(f"typos auto-off: {why_not}")
        return False
    return True


async def type_step_text(ctx: RunContext, console: Console, step: TypingStep, text: str, *,
                         enter: bool, enter_newlines: bool = False,
                         secret: bool = False) -> bool:
    """type_text with the step's typing options."""
    return await type_text(ctx, console, text, typing=step.typing, typos_off=step.typos_off,
                           key=step.path_str(), enter=enter, enter_newlines=enter_newlines,
                           secret=secret)


async def type_text(ctx: RunContext, console: Console, text: str, *,
                    typing: TypingSpec | None, typos_off: bool, key: str, enter: bool,
                    enter_newlines: bool = False, secret: bool = False) -> bool:
    """Type `text` (and press Enter if asked). Returns True if the last line was typed on a
    shell command line and verified before Enter. `key` seeds reproducible randomness."""
    await ctx.activate(console)
    params = ctx.typing_params(console, typing)
    rng = ctx.rng(key, params)
    lines = text.split("\n") if enter_newlines else [text]
    await ctx.sleep(think_time(text, params, rng))
    verified = False
    for index, line in enumerate(lines):
        press = enter or index < len(lines) - 1
        info = await console.info()
        before_cursor = await console.current_line_before_cursor(info)
        if info.alternate_on:
            at_shell, why_not = False, "full-screen program (alternate screen)"
        elif not console.prompt_matches(before_cursor):
            at_shell, why_not = False, "not at a shell prompt"
        else:
            at_shell, why_not = True, ""
        if secret:
            at_shell, why_not = False, "secret value"
        console.input_start = (info.cursor_abs, info.cursor_x) if at_shell else None
        can_verify = at_shell and press
        if at_shell and not press:
            why_not = "no Enter in this step, so the line is not checked before running"
        typos = typos_gate(ctx, params, typos_off or secret, can_verify, why_not)
        await _mark_input(console)
        plan = plan_line(line, params, rng, ctx.speed, typos=typos)
        for typo in plan.typos:
            ctx.log("info", "  " + typo.describe())
        for word in plan.rewords:
            ctx.log("info", f"  reworded {word!r} (backspaced and retyped)")
        await send_keystrokes(console, plan.events)
        verified = False
        if press:
            if console.input_start is not None:
                await verify_line(ctx, console, line)
                verified = True
            await press_enter(ctx, console)
        else:
            console.output_start = (await console.info()).cursor_abs
        if index < len(lines) - 1:
            await asyncio.sleep(0.15)
    return verified


async def _read_until(console: Console, expected: str, timeout: float) -> str | None:
    """Poll the command line until it shows `expected` (echo can lag) or time runs out."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    got = await console.read_input()
    while got != expected and loop.time() < deadline:
        await asyncio.sleep(0.05)
        got = await console.read_input()
    return got


async def verify_line(ctx: RunContext, console: Console, expected: str) -> None:
    """Spec 6.2: before Enter, the command line must show exactly the intended text."""
    got = await _read_until(console, expected, VERIFY_TIMEOUT)
    if got == expected:
        return
    ctx.log("warning", f"command line shows {got!r} instead of {expected!r}; retyping it")
    await console.send_key("C-u")
    await asyncio.sleep(0.1)
    fast = resolve_typing([FAST])
    await send_keystrokes(console, plan_typing(expected, fast, random.Random(), ctx.speed))
    got = await _read_until(console, expected, VERIFY_TIMEOUT)
    if got != expected:
        raise StepFailed("the command line does not show the intended text; Enter was not "
                         "pressed", intended=expected, screen=got)


async def paste_text(ctx: RunContext, console: Console, text: str, *, enter: bool) -> None:
    """Instantly insert `text` at the cursor (a pseudo-paste: all characters in one send,
    no per-character typing). Character-safe; not the OS clipboard or bracketed paste."""
    await ctx.activate(console)
    info = await console.info()
    at_shell = not info.alternate_on and console.prompt_matches(
        await console.current_line_before_cursor(info))
    console.input_start = (info.cursor_abs, info.cursor_x) if at_shell else None
    await _mark_input(console)
    if text:
        await console.send_text(text)
    await asyncio.sleep(0.05)          # let the pane repaint before Enter
    if enter:
        await press_enter(ctx, console)
    else:
        console.output_start = (await console.info()).cursor_abs


async def press_tab(ctx: RunContext, console: Console) -> None:
    """Press Tab (shell autocomplete). The completion is left on the line for a following
    `wait_for`/`expect` or Enter."""
    await ctx.activate(console)
    await console.send_key("Tab")


async def press_enter(ctx: RunContext, console: Console, count: int = 1) -> None:
    await ctx.activate(console)
    info = await console.info()
    console.output_start = info.cursor_abs + 1
    await _mark_input(console)
    for i in range(count):
        await console.send_key("Enter")
        if i < count - 1:
            await ctx.sleep(0.15)
    console.input_start = None


async def press_key(ctx: RunContext, console: Console, key: str, repeat: int = 1) -> None:
    await ctx.activate(console)
    info = await console.info()
    console.output_start = info.cursor_abs
    await _mark_input(console)
    for i in range(repeat):
        await console.send_key(key)
        if i < repeat - 1:
            await ctx.sleep(0.12)
    console.input_start = None
