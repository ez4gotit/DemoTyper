"""Automatic answers: type a reply whenever a known prompt appears during a wait.

Typical use is the sudo password:

    defaults:
      answers:
        - when: '\\[sudo\\] password for'
          secret: SUDO_PASS

Rules are checked on every poll of every wait, against the text before the cursor, which is
where a program that asks something leaves the cursor. Each prompt position is answered
once. A secret answer is typed only into hidden input (see Console.input_hidden), and a
second prompt for the same secret within one wait fails the step: the secret was rejected,
and trying again would only repeat the failure on camera.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..errors import StepFailed
from ..loader.model import AnswerRule
from .input import type_text

if TYPE_CHECKING:
    from ..console import Console
    from .context import RunContext


@dataclass
class AnswerState:
    """Per-wait bookkeeping."""

    answered_line: int | None = None  # absolute line of the prompt last answered
    secret_answers: dict[int, int] = field(default_factory=dict)  # rule index -> count
    waiting_logged: set[int] = field(default_factory=set)


class Responder:
    def __init__(self, ctx: RunContext):
        self.ctx = ctx

    def rules(self, console: Console) -> list[AnswerRule]:
        return [*console.spec.answers, *self.ctx.defaults.answers]

    async def poll(self, console: Console, state: AnswerState) -> bool:
        """Answer a prompt if one is showing. Returns True if something was typed."""
        rules = self.rules(console)
        if not rules:
            return False
        info = await console.info()
        if info.alternate_on or info.dead:
            return False
        line = await console.current_line_before_cursor(info)
        if not line.strip():
            return False
        for index, rule in enumerate(rules):
            if not re.search(rule.when, line):
                continue
            if state.answered_line == info.cursor_abs:
                return False  # answered; the program has not moved on yet
            if rule.secret is not None:
                if state.secret_answers.get(index, 0) >= 1:
                    raise StepFailed(
                        f"the prompt {line.strip()!r} came back after secret {rule.secret} "
                        "was typed: the secret was not accepted",
                        expected=f"no second prompt matching {rule.when!r}",
                        console=console.name)
                if not await console.input_hidden():
                    if index not in state.waiting_logged:
                        state.waiting_logged.add(index)
                        self.ctx.log("debug", f"prompt {line.strip()!r} matches, waiting for "
                                              "hidden input before typing the secret")
                    return False
                state.secret_answers[index] = state.secret_answers.get(index, 0) + 1
                answer, shown = self.ctx.secrets[rule.secret], f"secret {rule.secret}"
            else:
                answer, shown = rule.text or "", repr(rule.text)
            self.ctx.note(f"answering {line.strip()!r} with {shown}")
            await type_text(self.ctx, console, answer, typing=None, typos_off=True,
                            key=f"answer:{index}", enter=rule.enter,
                            secret=rule.secret is not None)
            state.answered_line = info.cursor_abs
            return True
        return False
