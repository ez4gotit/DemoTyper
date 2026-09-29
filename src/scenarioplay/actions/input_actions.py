"""Actions that send input: run, type, enter, key, clear."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Literal

from pydantic import Field, PositiveInt

from ..conditions.screen import PromptCondition
from ..console.tmux import tmux_key
from ..engine.input import (
    paste_text,
    press_enter,
    press_key,
    press_tab,
    type_step_text,
    type_text,
    wait_hidden_input,
)
from ..errors import StepFailed
from ..loader.model import SECRET_NAME, Strict
from ..plugins import action
from .base import InputStep, TypingStep, text_problem
from .data_actions import IDENT, CaptureSpec, extract, store

if TYPE_CHECKING:
    from ..console import Console
    from ..engine.context import RunContext
    from ..loader.checks import Checker


async def _after_prompt(ctx: RunContext, console: Console, *, command: str | None,
                        check_exit: bool) -> None:
    """Read the hook's report once the prompt is back: exit code, executed command line."""
    status = await console.status()
    if status is None or not console.hook_ok:
        return
    ctx.last.exit_code = status.exit_code
    if command is not None and status.command.strip() != command.strip():
        # Should never happen: the command line is verified before Enter (spec 6.2).
        ctx.executed_mismatches.append({"intended": command, "executed": status.command})
        ctx.log("error", f"the shell ran {status.command!r} but the scenario typed "
                         f"{command!r}")
    if check_exit and status.exit_code != 0:
        raise StepFailed(f"the command exited with code {status.exit_code}",
                         exit_code=status.exit_code, expected="exit code 0")


@action
class RunStep(TypingStep):
    """Type a command, press Enter and wait for the prompt (or for `expect` / `wait_for`)."""

    KEYWORD = "run"
    NO_RENDER = frozenset({"capture"})
    run: str
    check_exit: bool = False
    capture: str | CaptureSpec | None = Field(
        None, description="Store the command's output in a variable: a name, or "
                          "{name, regex, group, lines}. Needs the prompt to come back.")

    def check(self, checker: Checker) -> None:
        if self.capture is not None and self.post_wait is not None and \
                not isinstance(self.post_wait, PromptCondition):
            checker.error(self, "`capture` needs the command to finish, so it cannot be "
                                "combined with a wait for something other than the prompt",
                          "capture")
        if isinstance(self.capture, str) and not re.fullmatch(IDENT, self.capture):
            checker.error(self, f"{self.capture!r} is not a valid variable name", "capture")
        super().check(checker)
        self.check_text(checker, self.run, newlines_ok=False)
        if self.check_exit and self.post_wait is not None and \
                not isinstance(self.post_wait, PromptCondition):
            checker.error(self, "`check_exit` needs the command to finish, so it cannot be "
                                "combined with a wait for something other than the prompt",
                          "check_exit")
        name = self.console or checker.scenario.consoles[0].name
        spec = next((c for c in checker.scenario.consoles if c.name == name), None)
        if self.check_exit and spec is not None and spec.shell == "sh":
            checker.error(self, "`check_exit` needs a bash or zsh console", "check_exit")
        if self.check_exit and spec is not None and spec.host:
            checker.error(self, "`check_exit` needs the hidden shell hook, which cannot be "
                                "installed on another machine; check with `exec` or "
                                "`expect` instead", "check_exit")

    async def execute(self, ctx: RunContext) -> None:
        problem = text_problem(self.run, newlines_ok=False)
        if problem:  # templates can bring in characters the loader never saw
            raise StepFailed(f"after filling in variables, {problem}")
        console = ctx.console_for(self)
        verified = await type_step_text(ctx, console, self, self.run, enter=True)
        cond = self.post_wait or PromptCondition()
        await ctx.wait(cond, self, console)
        if isinstance(cond, PromptCondition):
            ctx.last.output = await console.command_output()
            await _after_prompt(ctx, console, command=self.run if verified else None,
                                check_exit=self.check_exit)
            if self.capture is not None:
                spec = CaptureSpec(name=self.capture) if isinstance(self.capture, str) \
                    else self.capture
                store(ctx, spec.name, extract(ctx.last.output, spec))
        await ctx.sleep(ctx.defaults.after_command_pause)


@action
class TypeStep(TypingStep):
    """Type text character by character. Press Enter only with `enter: true`.

    With `tab: true`, the text is typed as a *prefix* and then Tab is pressed so the shell
    autocompletes the rest (e.g. `type: "cat /etc/host"` + `tab: true` -> /etc/hostname).
    Pair it with `expect`/`wait_for` to confirm the completion; typos are off on the prefix
    so completion is not thrown off."""

    KEYWORD = "type"
    type: str
    enter: bool = False
    enter_newlines: bool = Field(
        False, description="Press Enter for each newline in the text. Without this, text "
                           "with newlines is refused.")
    tab: bool = Field(False, description="After typing, press Tab to autocomplete the rest.")

    def check(self, checker: Checker) -> None:
        super().check(checker)
        self.check_text(checker, self.type, newlines_ok=self.enter_newlines)
        if self.tab and self.enter_newlines:
            checker.error(self, "`tab` autocompletes one line; it can't be combined with "
                                "`enter_newlines`", "tab")

    async def execute(self, ctx: RunContext) -> None:
        console = ctx.console_for(self)
        if self.tab:
            # Type the prefix cleanly (no typos, no Enter), then let the shell complete it.
            await type_text(ctx, console, self.type, typing=self.typing, typos_off=True,
                            key=self.path_str(), enter=False)
            await press_tab(ctx, console)
            if self.post_wait is not None:
                await ctx.wait(self.post_wait, self, console)
            if self.enter:
                await press_enter(ctx, console)
            return
        await type_step_text(ctx, console, self, self.type, enter=self.enter,
                        enter_newlines=self.enter_newlines)
        if self.post_wait is not None:
            await ctx.wait(self.post_wait, self, console)


class PasteBuffer(Strict):
    buffer: str = Field(description="Name of a `defaults.buffers` entry to insert.")


@action
class PasteStep(InputStep):
    """Instantly insert a substring at the cursor (a pseudo-paste) instead of typing it
    character by character - handy for long, boring tokens (a base64 blob, a long path).

    `paste: "text"` inserts literal text (templates allowed); `paste: {buffer: name}`
    inserts a named buffer from `defaults.buffers`. It is character-safe and does not use
    the OS clipboard or bracketed paste - the characters are just sent in one burst."""

    KEYWORD = "paste"
    paste: str | PasteBuffer
    enter: bool = False

    def summary(self) -> str:
        if isinstance(self.paste, PasteBuffer):
            return f"paste: buffer {self.paste.buffer}"
        text = self.paste if len(self.paste) <= 40 else self.paste[:37] + "..."
        return f"paste: {text!r}"

    def check(self, checker: Checker) -> None:
        super().check(checker)
        if isinstance(self.paste, PasteBuffer):
            if self.paste.buffer not in checker.scenario.defaults.buffers:
                known = ", ".join(sorted(checker.scenario.defaults.buffers)) or "none"
                checker.error(self, f"no buffer {self.paste.buffer!r} in defaults.buffers "
                                    f"(defined: {known})", "paste")
        elif "{{" not in self.paste:
            problem = text_problem(self.paste, newlines_ok=False)
            if problem:
                checker.error(self, problem, "paste")

    async def execute(self, ctx: RunContext) -> None:
        console = ctx.console_for(self)
        text = ctx.buffer(self.paste.buffer) if isinstance(self.paste, PasteBuffer) \
            else self.paste
        problem = text_problem(text, newlines_ok=False)
        if problem:
            raise StepFailed(f"cannot paste: {problem}")
        await paste_text(ctx, console, text, enter=self.enter)
        ctx.note(f"pasted {len(text)} characters instantly")
        if self.post_wait is not None:
            await ctx.wait(self.post_wait, self, console)


@action
class SecretStep(TypingStep):
    """Type a secret (a password) by name. Shown on screen as the program shows it (a
    password prompt shows nothing); masked as **** in every output.

    The step first waits until the terminal reads input without echo, so a secret is never
    typed where it would be visible. `hidden: false` drops that check."""

    KEYWORD = "secret"
    secret: str = Field(pattern=SECRET_NAME)
    enter: bool = False
    hidden: bool = True

    def summary(self) -> str:
        return f"secret: {self.secret} (****)"

    async def execute(self, ctx: RunContext) -> None:
        console = ctx.console_for(self)
        if self.hidden:
            await wait_hidden_input(ctx, console, self.timeout or ctx.defaults.timeout)
        await type_text(ctx, console, ctx.secrets[self.secret], typing=self.typing,
                        typos_off=True, key=self.path_str(), enter=self.enter, secret=True)
        if self.post_wait is not None:
            await ctx.wait(self.post_wait, self, console)


@action
class EnterStep(InputStep):
    """Press Enter (`enter: true`, or `enter: 3` to press it three times)."""

    KEYWORD = "enter"
    PRIORITY = 1  # also an option of `type` and `secret`
    enter: bool | PositiveInt = True

    def check(self, checker: Checker) -> None:
        super().check(checker)
        if self.enter is False:
            checker.error(self, "`enter: false` does nothing; remove the step", "enter")

    async def execute(self, ctx: RunContext) -> None:
        console = ctx.console_for(self)
        count = 1 if self.enter is True else int(self.enter)
        await press_enter(ctx, console, count)
        if self.post_wait is not None:
            await ctx.wait(self.post_wait, self, console)


@action
class KeyStep(InputStep):
    """Send a key or combination: C-c, C-d, C-l, Tab, Up, Down, Escape, F1-F12, M-x..."""

    KEYWORD = "key"
    key: str
    repeat: PositiveInt = 1

    def check(self, checker: Checker) -> None:
        super().check(checker)
        if tmux_key(self.key) is None:
            checker.error(self, f"unknown key {self.key!r}; examples: C-c, Tab, Up, Escape, "
                                "F5, M-x, PageDown", "key")

    async def execute(self, ctx: RunContext) -> None:
        console = ctx.console_for(self)
        key = tmux_key(self.key)
        assert key is not None
        await press_key(ctx, console, key, self.repeat)
        if self.post_wait is not None:
            await ctx.wait(self.post_wait, self, console)


@action
class ClearStep(TypingStep):
    """Clear the console: `clear: command` (or `true`) types `clear`, `clear: key` sends
    Ctrl+L."""

    KEYWORD = "clear"
    clear: Literal["command", "key"] | Literal[True] = "command"

    async def execute(self, ctx: RunContext) -> None:
        console = ctx.console_for(self)
        if self.clear == "key":
            await press_key(ctx, console, "C-l")
            await ctx.sleep(0.3)
        else:
            await type_step_text(ctx, console, self, "clear", enter=True)
            await ctx.wait(PromptCondition(), self, console)
        if self.post_wait is not None:
            await ctx.wait(self.post_wait, self, console)
