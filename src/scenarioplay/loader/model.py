"""Pydantic models for the scenario file's top-level keys (spec section 5)."""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeFloat,
    PositiveFloat,
    PositiveInt,
    field_validator,
    model_validator,
)

DEFAULT_PROMPT = r"[$#%>] ?$"
CONSOLE_NAME = r"^[A-Za-z_][A-Za-z0-9_-]*$"
SECRET_NAME = r"^[A-Za-z_][A-Za-z0-9_]*$"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


def _ordered_pair(v: tuple[float, float]) -> tuple[float, float]:
    lo, hi = v
    if lo < 0 or hi < lo:
        raise ValueError("expected [min, max] with 0 <= min <= max")
    return v


Range = Annotated[tuple[float, float], AfterValidator(_ordered_pair)]
IntRange = Annotated[tuple[int, int], AfterValidator(_ordered_pair)]


def check_regex(value: str) -> str:
    try:
        re.compile(value)
    except re.error as e:
        raise ValueError(f"invalid regular expression: {e}") from None
    return value


Regex = Annotated[str, AfterValidator(check_regex)]


# --- typing (section 6.3) -------------------------------------------------------------

TypoKind = Literal["neighbour", "transposition", "doubled", "missed", "case"]


class TyposSpec(Strict):
    enabled: bool | None = None
    rate: Annotated[float, Field(ge=0, le=1)] | None = None
    kinds: dict[TypoKind, NonNegativeFloat] | None = None
    notice_after: IntRange | None = None
    hesitation: Range | None = None
    backspace_cps: PositiveFloat | None = None
    max_per_line: Annotated[int, Field(ge=0)] | None = None
    min_length: Annotated[int, Field(ge=0)] | None = None
    protect: list[str] | None = None
    seed: int | None = None


class BurstSpec(Strict):
    chance: Annotated[float, Field(ge=0, le=1)] | None = None
    speedup: Annotated[float, Field(ge=1)] | None = None
    length: IntRange | None = None


class TypingSpec(Strict):
    """Typing parameters; every field is optional so specs can be layered."""

    profile: Literal["novice", "normal", "expert", "robot"] | None = None
    cps: PositiveFloat | None = None
    jitter: Annotated[float, Field(ge=0, le=2)] | None = None
    word_pause: Range | None = None
    punctuation_pause: Range | None = None
    shifted_slowdown: Annotated[float, Field(ge=1)] | None = None
    think_before: Range | None = None
    think_long_threshold: Annotated[int, Field(ge=0)] | None = None
    burst: BurstSpec | None = None
    layout: str | None = None
    typos: TyposSpec | None = None


# --- target (section 4) ---------------------------------------------------------------


class SshSpec(Strict):
    host: str = "auto"
    user: str | None = None
    key: str | None = None
    port: PositiveInt = 22
    options: list[str] = Field(
        default_factory=list, description="Extra ssh options, e.g. ['-o', 'ProxyJump=bastion'].")
    program: str = Field("ssh", description="The ssh client to run.")
    known_hosts: str | None = Field(
        "~/.ssh/known_hosts", description="Host keys to check the guest against (vmware "
                                          "target); `none` accepts any key.")


class TerminalSpec(Strict):
    """The full-screen terminal window that shows the tmux session."""

    command: list[str] | str | None = Field(
        None,
        description="Terminal command. A string may contain {attach}; a list gets the attach "
        "command appended. Default: the first installed of xterm, alacritty, kitty, "
        "gnome-terminal, xfce4-terminal, konsole.",
    )
    font: str = "Monospace"
    font_size: PositiveInt = 16


class RecorderSpec(Strict):
    backend: Literal["auto", "x11grab", "wf-recorder"] = Field(
        "auto", description="auto: x11grab, or wf-recorder on a Wayland session that has it.")
    display: str | None = Field(
        None, description="X display to record (default $DISPLAY), or for wf-recorder an "
                          "output name such as eDP-1.")
    fps: PositiveInt = 30
    crf: Annotated[int, Field(ge=0, le=51)] = 23
    codec: str = "libx264"
    preset: str = "veryfast"
    lead_in: NonNegativeFloat = 2.0
    tail: NonNegativeFloat = 2.0
    draw_mouse: bool = False


class TargetSpec(Strict):
    kind: Literal["local", "vmware"] = "local"
    vmx: str | None = None
    snapshot: str | None = None
    ssh: SshSpec | None = None
    record: Literal["guest", "host"] = "guest"
    boot_timeout: PositiveFloat = 180.0
    terminal: TerminalSpec = Field(default_factory=TerminalSpec)
    recorder: RecorderSpec = Field(default_factory=RecorderSpec)

    @model_validator(mode="after")
    def _vmware_needs_vmx(self) -> TargetSpec:
        if self.kind == "vmware" and not self.vmx:
            raise ValueError("target.kind vmware needs target.vmx")
        return self


class OnFailRetry(Strict):
    """`on_fail: {retry: 3, delay: 2}`: run the failed step again, up to `retry` times."""

    retry: PositiveInt
    delay: NonNegativeFloat = 1.0


# --- automatic answers ---------------------------------------------------------------


class AnswerRule(Strict):
    """Answer a prompt automatically whenever it appears while a step waits.

    `when` is a regex matched against the text before the cursor, where a program that
    asks something leaves it. The answer is typed like any other input, then Enter.
    """

    when: Regex = Field(description="Regex for the prompt, e.g. '\\[sudo\\] password for'.")
    secret: Annotated[str, Field(pattern=SECRET_NAME)] | None = Field(
        None, description="Name of a secret to type. Typed only into hidden input (the "
                          "terminal is not echoing); a second prompt in the same wait fails "
                          "the step, since the secret was rejected.")
    text: str | None = Field(None, description="Plain text to type, such as `y`.")
    enter: bool = True

    @model_validator(mode="after")
    def _one_answer(self) -> AnswerRule:
        if (self.secret is None) == (self.text is None):
            raise ValueError("an answer needs exactly one of `secret` or `text`")
        if self.text is not None and any(ord(c) < 32 or ord(c) == 127 for c in self.text):
            raise ValueError("`text` cannot contain control characters or newlines")
        return self


# --- the rest ------------------------------------------------------------------------


class Meta(BaseModel):
    model_config = ConfigDict(extra="allow")

    title: str | None = None
    source_pdf: str | None = None
    author: str | None = None


class Defaults(Strict):
    typing: TypingSpec | None = None
    prompt: Regex = DEFAULT_PROMPT
    timeout: PositiveFloat = 60.0
    interval: PositiveFloat = 0.2
    after_command_pause: NonNegativeFloat = 1.0
    on_fail: Literal["fail", "continue"] | OnFailRetry = "fail"
    keep_video_on_fail: bool = True
    clear_after_setup: bool = Field(
        True, description="Clear each console after `setup`, so the video starts clean."
    )
    answers: list[AnswerRule] = Field(
        default_factory=list, description="Prompts answered automatically in every console.")


class ConsoleSpec(Strict):
    name: Annotated[str, Field(pattern=CONSOLE_NAME)]
    title: str | None = None
    shell: Literal["bash", "zsh", "sh"] = "bash"
    cwd: str = "~"
    prompt: Regex | None = None
    env: dict[str, str] = Field(default_factory=dict)
    typing: TypingSpec | None = None
    answers: list[AnswerRule] = Field(
        default_factory=list, description="Prompts answered automatically in this console; "
                                          "checked before `defaults.answers`.")
    host: str | None = Field(
        None, description="Run this console on another machine: `host` or `user@host`. The "
                          "runner opens it with ssh inside the pane (key-based login).")
    ssh: SshSpec | None = Field(None, description="Options for `host`: user, key, port.")
    size: Annotated[str, Field(pattern=r"^\d+%?$")] | int | None = Field(
        None, description="Pane size in split layouts: `30%` or a number of cells.")
    start: bool = Field(True, description="Open at the start; false = open later with "
                                          "`open_console`.")

    @field_validator("env")
    @classmethod
    def _env_names(cls, v: dict[str, str]) -> dict[str, str]:
        for name in v:
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                raise ValueError(f"invalid environment variable name {name!r}")
        return v


Layout = Literal["single", "split-horizontal", "split-vertical", "grid", "tabs"]


class Scenario(Strict):
    """The whole scenario file. Step lists stay raw here; loader.steps parses them."""

    version: Literal[1] = 1
    meta: Meta = Field(default_factory=Meta)
    target: TargetSpec = Field(default_factory=TargetSpec)
    defaults: Defaults = Field(default_factory=Defaults)
    layout: Layout = "single"
    consoles: list[ConsoleSpec] = Field(default_factory=lambda: [ConsoleSpec(name="main")])
    vars: dict[str, Any] = Field(default_factory=dict)
    setup: list[Any] = Field(default_factory=list)
    steps: Annotated[list[Any], Field(min_length=1)]
    finally_: list[Any] = Field(default_factory=list, alias="finally")

    @field_validator("consoles")
    @classmethod
    def _unique_consoles(cls, v: list[ConsoleSpec]) -> list[ConsoleSpec]:
        if not v:
            raise ValueError("at least one console is needed")
        seen: set[str] = set()
        for c in v:
            if c.name in seen:
                raise ValueError(f"console name {c.name!r} is used twice")
            seen.add(c.name)
        if not v[0].start:
            raise ValueError("the first console must start open (`start: true`)")
        return v
