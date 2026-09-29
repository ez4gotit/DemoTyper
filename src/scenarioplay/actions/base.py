"""Base classes for step plugins: actions and control blocks."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Union

from pydantic import BaseModel, PositiveFloat, PrivateAttr

from ..errors import Location
from ..lang import Env, ExprError, Node, parse_template
from ..loader.model import OnFailRetry, Strict, TypingSpec

if TYPE_CHECKING:
    from ..conditions.base import Condition
    from ..engine.context import RunContext
    from ..loader.checks import Checker

# A "check" is what `when`, `if`, `while`, `until` and `assert` take: an expression string,
# or a screen/system condition mapping checked once (spec 8).
Check = Union[Node, "Condition"]

# Common options that are never template-rendered (names, not text).
_NO_RENDER_COMMON = frozenset({"console", "label", "when", "on_fail", "timeout"})


def render_value(value: Any, env: Env, *, native: bool = False) -> Any:
    """Render {{ }} templates inside a value: strings, and strings in lists and dicts."""
    if isinstance(value, str):
        template = parse_template(value)
        if template.is_static:
            return value
        return template.render(env, native=native)
    if isinstance(value, list):
        return [render_value(v, env, native=native) for v in value]
    if isinstance(value, dict):
        return {k: render_value(v, env, native=native) for k, v in value.items()}
    return value


class StepModel(Strict):
    """One step. The field named after KEYWORD holds the step's main argument; the other
    fields are its options plus the common options below (spec section 6)."""

    KEYWORD: ClassVar[str] = ""
    # 0 = the keyword is only an action. Higher values mark keywords that are also options of
    # other steps (`enter`, `wait_for`); when a step holds several keywords, the lowest wins.
    PRIORITY: ClassVar[int] = 0
    # Fields holding a wait condition, parsed by the loader into `conditions`.
    CONDITION_FIELDS: ClassVar[tuple[str, ...]] = ()
    # Fields holding a check (expression or condition), parsed into `checks`. `when` always.
    CHECK_FIELDS: ClassVar[tuple[str, ...]] = ()
    # Fields holding nested step lists, parsed into `children`.
    STEP_LIST_FIELDS: ClassVar[tuple[str, ...]] = ()
    # Fields that are names, not text: never template-rendered.
    NO_RENDER: ClassVar[frozenset[str]] = frozenset()
    # Fields rendered to native values: a single {{ expr }} keeps its type.
    NATIVE: ClassVar[frozenset[str]] = frozenset()
    # Control blocks render their own arguments when they run (loop variables change).
    IS_BLOCK: ClassVar[bool] = False
    # Loops accept `break` and `continue` inside them.
    IS_LOOP: ClassVar[bool] = False

    console: str | None = None
    timeout: PositiveFloat | None = None
    on_fail: Literal["fail", "continue"] | OnFailRetry | list[Any] | None = None
    when: str | dict[str, Any] | bool | None = None
    label: str | None = None

    _path: tuple[Any, ...] = PrivateAttr(default=())
    _loc: Location | None = PrivateAttr(default=None)
    _conditions: dict[str, Condition] = PrivateAttr(default_factory=dict)
    _checks: dict[str, Check] = PrivateAttr(default_factory=dict)
    _children: dict[str, list[StepModel]] = PrivateAttr(default_factory=dict)
    _on_fail_steps: list[StepModel] | None = PrivateAttr(default=None)

    @property
    def path(self) -> tuple[Any, ...]:
        return self._path

    @property
    def loc(self) -> Location | None:
        return self._loc

    @property
    def conditions(self) -> dict[str, Condition]:
        return self._conditions

    @property
    def checks(self) -> dict[str, Check]:
        return self._checks

    @property
    def main(self) -> Any:
        return getattr(self, self.KEYWORD)

    def children(self) -> Iterator[tuple[str, list[StepModel]]]:
        """Nested step lists, including `on_fail` recovery steps."""
        yield from self._children.items()
        if self._on_fail_steps is not None:
            yield "on_fail", self._on_fail_steps

    def summary(self) -> str:
        value = self.main
        text = value if isinstance(value, str) else repr(value)
        text = text.replace("\n", "\\n")  # one log line per step
        if len(text) > 70:
            text = text[:67] + "..."
        return f"{self.KEYWORD}: {text}"

    def path_str(self) -> str:
        return ".".join(str(p) for p in self._path)

    def rendered(self, env: Env) -> StepModel:
        """A copy with {{ }} templates in its text fields filled in (spec 5.1)."""
        skip = (_NO_RENDER_COMMON | self.NO_RENDER | set(self.CHECK_FIELDS)
                | set(self.STEP_LIST_FIELDS) | set(self.CONDITION_FIELDS))
        updates = {}
        for name, info in type(self).model_fields.items():
            if name in skip or (info.alias or name) in skip:
                continue
            value = getattr(self, name)
            if isinstance(value, BaseModel):
                continue
            new = render_value(value, env, native=name in self.NATIVE)
            if new is not value:
                updates[name] = new
        copy = self.model_copy(update=updates)
        copy._conditions = {k: c.rendered(env) for k, c in self._conditions.items()}
        return copy

    def child_names(self, field: str) -> set[str]:
        """Variables a block defines for the steps in `field` (loop variables, params)."""
        return set()

    def check(self, checker: Checker) -> None:
        """Semantic checks beyond the field types. Report through checker.error/warning."""

    async def execute(self, ctx: RunContext) -> None:
        raise NotImplementedError


class BlockStep(StepModel):
    """A control block (spec 8): holds nested steps and runs them itself."""

    IS_BLOCK = True

    def summary(self) -> str:
        value = self.main
        if isinstance(value, (dict, list)) and not isinstance(value, str):
            text = repr(value)
        else:
            text = str(value)
        if len(text) > 60:
            text = text[:57] + "..."
        return f"{self.KEYWORD}: {text}"


class InputStep(StepModel):
    """A step that sends input to a console and may wait afterwards (`wait_for` or its
    alias `expect`; a bare string is a regex)."""

    CONDITION_FIELDS = ("wait_for", "expect")

    wait_for: dict[str, Any] | str | None = None
    expect: dict[str, Any] | str | None = None

    def check(self, checker: Checker) -> None:
        if self.wait_for is not None and self.expect is not None:
            checker.error(self, "use either `wait_for` or `expect`, not both", "expect")

    @property
    def post_wait(self) -> Condition | None:
        return self._conditions.get("wait_for") or self._conditions.get("expect")


class TypingStep(InputStep):
    """An input step that types text."""

    typing: TypingSpec | None = None
    typos: bool | Literal["on", "off"] | None = None

    @property
    def typos_off(self) -> bool:
        return self.typos in (False, "off")

    def check_text(self, checker: Checker, text: str, *, newlines_ok: bool) -> None:
        if not text:
            checker.error(self, "the text is empty", self.KEYWORD)
        problem = text_problem(text, newlines_ok=newlines_ok)
        if problem:
            checker.error(self, problem, self.KEYWORD)
        if secret_paths(text):
            checker.error(self, "a secret in typed text would be visible on screen and in "
                                "the shell history; use a `secret` step or an answer rule",
                          self.KEYWORD)


def secret_paths(text: str) -> set[str]:
    """The `secret.NAME` paths a template reads (empty for invalid templates)."""
    try:
        return {p for p in parse_template(text).paths() if p.startswith("secret.")}
    except ExprError:
        return set()


def text_problem(text: str, *, newlines_ok: bool) -> str | None:
    """Why this text cannot be typed as is, or None."""
    for ch in text:
        if ch == "\n" and newlines_ok:
            continue
        if ch == "\n":
            return ("the text contains a newline; use `type` with `enter_newlines: true` to "
                    "type several lines")
        if ch == "\t":
            return ("the text contains a Tab, which would trigger completion; use a "
                    "`key: Tab` step instead")
        if ord(ch) < 32 or ord(ch) == 127:
            return f"the text contains control character {ch!r}; send keys with a `key` step"
    return None
