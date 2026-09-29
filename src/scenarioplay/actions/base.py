"""Base class for step plugins (actions and, later, control blocks)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, Literal

from pydantic import PositiveFloat, PrivateAttr

from ..errors import Location
from ..loader.model import Strict, TypingSpec

if TYPE_CHECKING:
    from ..conditions.base import Condition
    from ..engine.context import RunContext
    from ..loader.checks import Checker


class StepModel(Strict):
    """One step. The field named after KEYWORD holds the step's main argument; the other
    fields are its options plus the common options below (spec section 6)."""

    KEYWORD: ClassVar[str] = ""
    # 0 = the keyword is only an action. Higher values mark keywords that are also options of
    # other steps (`enter`, `wait_for`); when a step holds several keywords, the lowest wins.
    PRIORITY: ClassVar[int] = 0
    # Fields holding a wait condition, parsed by the loader into `conditions`.
    CONDITION_FIELDS: ClassVar[tuple[str, ...]] = ()

    console: str | None = None
    timeout: PositiveFloat | None = None
    on_fail: Literal["fail", "continue"] | None = None
    when: Any = None
    label: str | None = None

    _path: tuple[Any, ...] = PrivateAttr(default=())
    _loc: Location | None = PrivateAttr(default=None)
    _conditions: dict[str, Condition] = PrivateAttr(default_factory=dict)

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
    def main(self) -> Any:
        return getattr(self, self.KEYWORD)

    def summary(self) -> str:
        value = self.main
        text = value if isinstance(value, str) else repr(value)
        if len(text) > 70:
            text = text[:67] + "..."
        return f"{self.KEYWORD}: {text}"

    def path_str(self) -> str:
        return ".".join(str(p) for p in self._path)

    def check(self, checker: Checker) -> None:
        """Semantic checks beyond the field types. Report through checker.error/warning."""

    async def execute(self, ctx: RunContext) -> None:
        raise NotImplementedError


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
        for ch in text:
            if ch == "\n" and newlines_ok:
                continue
            if ch == "\n":
                checker.error(self, "the text contains a newline; use `type` with "
                                    "`enter_newlines: true` to type several lines", self.KEYWORD)
                return
            if ch == "\t":
                checker.error(self, "the text contains a Tab, which would trigger completion; "
                                    "use a `key: Tab` step instead", self.KEYWORD)
                return
            if ord(ch) < 32 or ord(ch) == 127:
                checker.error(self, f"the text contains control character {ch!r}; send keys "
                                    "with a `key` step", self.KEYWORD)
                return
