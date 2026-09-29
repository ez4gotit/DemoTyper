"""The safe expression language (spec 5.2), shared by conditions and {{ }} templates.

    expr    := or
    or      := and ('or' and)*
    and     := not ('and' not)*
    not     := 'not' not | compare
    compare := filtered (('==' | '!=' | '<' | '<=' | '>' | '>=' | 'in' | 'not' 'in'
                          | 'matches') filtered)?
    filtered:= unary ('|' NAME ('(' args ')')?)*
    unary   := '-' unary | postfix
    postfix := primary ('.' NAME | '[' expr ']')*
    primary := NUMBER | STRING | true | false | null | NAME | '(' expr ')' | '[' items ']'

Values are plain data (str, int, float, bool, None, list, dict). There is no attribute
access on Python objects and no function calls other than the filters below.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any


class ExprError(ValueError):
    def __init__(self, message: str, pos: int | None = None):
        super().__init__(message)
        self.pos = pos


class Undefined:
    """A name or key that does not exist. Only `default` may consume it."""

    def __init__(self, path: str):
        self.path = path

    def __repr__(self) -> str:
        return f"Undefined({self.path})"


def _require(value: Any) -> Any:
    if isinstance(value, Undefined):
        root = value.path.split(".")[0].split("[")[0]
        hint = "" if root in ("env", "last", "loop", "take", "error", "secret") else \
            f"; declare it in `vars`, pass --var {root}=..., or set it with `set`/`capture`"
        raise ExprError(f"undefined variable '{value.path}'{hint}")
    return value


def _kind(value: Any) -> str:
    if isinstance(value, bool):
        return "true/false"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "text"
    if isinstance(value, list):
        return "list"
    if isinstance(value, Mapping):
        return "mapping"
    return "null" if value is None else type(value).__name__


# --- filters -----------------------------------------------------------------------------

def _join(value: Any, sep: str = "") -> str:
    if not isinstance(value, (list, tuple)):
        raise ExprError(f"join needs a list, got {_kind(value)}")
    return str(sep).join(to_text(v) for v in value)


def _int(value: Any) -> int:
    try:
        return int(str(value).strip()) if not isinstance(value, (int, float)) else int(value)
    except ValueError:
        raise ExprError(f"cannot turn {value!r} into a number") from None


def _length(value: Any) -> int:
    if isinstance(value, (str, list, tuple, Mapping)):
        return len(value)
    raise ExprError(f"length needs text, a list or a mapping, got {_kind(value)}")


def _text_filter(fn: Callable[[str], str], name: str) -> Callable[[Any], str]:
    def apply(value: Any) -> str:
        if not isinstance(value, str):
            raise ExprError(f"{name} needs text, got {_kind(value)}")
        return fn(value)
    return apply


FILTERS: dict[str, tuple[Callable[..., Any], int, int]] = {
    # name: (function, min args, max args) -- arguments after the piped value
    "join": (_join, 0, 1),
    "upper": (_text_filter(str.upper, "upper"), 0, 0),
    "lower": (_text_filter(str.lower, "lower"), 0, 0),
    "trim": (_text_filter(str.strip, "trim"), 0, 0),
    "default": (lambda v, d="": d if v is None else v, 0, 1),  # Undefined handled in Filter
    "length": (_length, 0, 0),
    "int": (_int, 0, 0),
    "string": (lambda v: to_text(v), 0, 0),
}


def to_text(value: Any) -> str:
    """How a value looks when put into text: true/false, empty for null, lists space-joined."""
    value = _require(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return " ".join(to_text(v) for v in value)
    return str(value)


# --- AST ---------------------------------------------------------------------------------

class Node:
    def eval(self, env: Env) -> Any:
        raise NotImplementedError

    def names(self) -> set[str]:
        """Root variable names this expression reads (for static checks)."""
        return set()

    def paths(self) -> set[str]:
        """Dotted paths such as secret.SUDO_PASS (for finding referenced secrets)."""
        return set()


@dataclass
class Literal(Node):
    value: Any

    def eval(self, env: Env) -> Any:
        return self.value


@dataclass
class Name(Node):
    name: str

    def eval(self, env: Env) -> Any:
        return env.lookup(self.name)

    def names(self) -> set[str]:
        return {self.name}

    def paths(self) -> set[str]:
        return {self.name}


@dataclass
class Attr(Node):
    base: Node
    attr: str

    def eval(self, env: Env) -> Any:
        base = self.base.eval(env)
        if isinstance(base, Undefined):
            return Undefined(f"{base.path}.{self.attr}")
        if isinstance(base, Mapping):
            if self.attr in base:
                return base[self.attr]
            return Undefined(f"{_path(self.base)}.{self.attr}")
        raise ExprError(f"cannot read .{self.attr} of {_kind(base)}")

    def names(self) -> set[str]:
        return self.base.names()

    def paths(self) -> set[str]:
        return {f"{p}.{self.attr}" for p in self.base.paths()}


@dataclass
class Index(Node):
    base: Node
    index: Node

    def eval(self, env: Env) -> Any:
        base = _require(self.base.eval(env))
        index = _require(self.index.eval(env))
        try:
            if isinstance(base, Mapping):
                return base[index] if index in base else \
                    Undefined(f"{_path(self.base)}[{index!r}]")
            if isinstance(base, (list, tuple, str)) and isinstance(index, int) \
                    and not isinstance(index, bool):
                return base[index]
        except IndexError:
            raise ExprError(f"index {index} is outside {_kind(base)} of length "
                            f"{len(base)}") from None
        raise ExprError(f"cannot index {_kind(base)} with {_kind(index)}")

    def names(self) -> set[str]:
        return self.base.names() | self.index.names()


@dataclass
class ListLit(Node):
    items: list[Node]

    def eval(self, env: Env) -> Any:
        return [_require(i.eval(env)) for i in self.items]

    def names(self) -> set[str]:
        return set().union(*(i.names() for i in self.items)) if self.items else set()


@dataclass
class Neg(Node):
    operand: Node

    def eval(self, env: Env) -> Any:
        v = _require(self.operand.eval(env))
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ExprError(f"cannot negate {_kind(v)}")
        return -v

    def names(self) -> set[str]:
        return self.operand.names()


@dataclass
class Not(Node):
    operand: Node

    def eval(self, env: Env) -> Any:
        return not truthy(self.operand.eval(env))

    def names(self) -> set[str]:
        return self.operand.names()


@dataclass
class BoolOp(Node):
    op: str  # and | or
    left: Node
    right: Node

    def eval(self, env: Env) -> Any:
        left = truthy(self.left.eval(env))
        if self.op == "and":
            return left and truthy(self.right.eval(env))
        return left or truthy(self.right.eval(env))

    def names(self) -> set[str]:
        return self.left.names() | self.right.names()


@dataclass
class Compare(Node):
    op: str
    left: Node
    right: Node

    def eval(self, env: Env) -> Any:
        a = _require(self.left.eval(env))
        b = _require(self.right.eval(env))
        op = self.op
        if op == "==":
            return a == b
        if op == "!=":
            return a != b
        if op in ("in", "not in"):
            if isinstance(b, str):
                if not isinstance(a, str):
                    raise ExprError(f"`in` text needs text on the left, got {_kind(a)}")
                result = a in b
            elif isinstance(b, (list, tuple, Mapping)):
                result = a in b
            else:
                raise ExprError(f"`in` needs text, a list or a mapping on the right, "
                                f"got {_kind(b)}")
            return result if op == "in" else not result
        if op == "matches":
            if not isinstance(b, str):
                raise ExprError("`matches` needs a regex string on the right")
            try:
                return re.search(b, to_text(a)) is not None
            except re.error as e:
                raise ExprError(f"invalid regular expression {b!r}: {e}") from None
        numeric = (int, float)
        if isinstance(a, bool) or isinstance(b, bool) or not (
                (isinstance(a, numeric) and isinstance(b, numeric))
                or (isinstance(a, str) and isinstance(b, str))):
            hint = " (captured values are text; use `| int`)" if \
                {type(a), type(b)} & {str} else ""
            raise ExprError(f"cannot compare {_kind(a)} {a!r} with {_kind(b)} {b!r}{hint}")
        return {"<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b}[op]

    def names(self) -> set[str]:
        return self.left.names() | self.right.names()


@dataclass
class Filter(Node):
    value: Node
    name: str
    args: list[Node]

    def eval(self, env: Env) -> Any:
        value = self.value.eval(env)
        args = [_require(a.eval(env)) for a in self.args]
        if self.name == "default":
            if isinstance(value, Undefined) or value is None:
                return args[0] if args else ""
            return value
        fn = FILTERS[self.name][0]
        return fn(_require(value), *args)

    def names(self) -> set[str]:
        names = self.value.names()
        for a in self.args:
            names |= a.names()
        return names

    def paths(self) -> set[str]:
        return self.value.paths()


def _path(node: Node) -> str:
    if isinstance(node, Name):
        return node.name
    if isinstance(node, Attr):
        return f"{_path(node.base)}.{node.attr}"
    return "value"


def truthy(value: Any) -> bool:
    return bool(_require(value))


class Env:
    """What a Name looks up. See lang.scope.Scope for the real one."""

    def lookup(self, name: str) -> Any:
        return Undefined(name)


# --- lexer and parser --------------------------------------------------------------------

_TOKEN = re.compile(r"""
    (?P<ws>\s+)
  | (?P<num>\d+\.\d+|\d+)
  | (?P<str>'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*")
  | (?P<op>==|!=|<=|>=|<|>|\(|\)|\[|\]|,|\.|\||-)
  | (?P<name>[A-Za-z_][A-Za-z0-9_]*)
""", re.X | re.S)
_KEYWORDS = {"and", "or", "not", "in", "matches", "true", "false", "null", "True", "False",
             "None"}
_ESCAPES = {"n": "\n", "t": "\t", "'": "'", '"': '"', "\\": "\\"}


def _unescape(body: str) -> str:
    # Unknown escapes keep their backslash, so regexes such as '\d+' work as written.
    return re.sub(r"\\(.)", lambda m: _ESCAPES.get(m.group(1), "\\" + m.group(1)), body,
                  flags=re.S)


@dataclass
class Tok:
    kind: str  # num | str | op | name | kw | end
    value: str
    pos: int


def tokenize(text: str) -> list[Tok]:
    tokens = []
    pos = 0
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m:
            raise ExprError(f"unexpected character {text[pos]!r}", pos)
        kind = m.lastgroup
        value = m.group(kind)
        if kind == "name" and value in _KEYWORDS:
            kind = "kw"
        if kind != "ws":
            tokens.append(Tok(kind, value, pos))
        pos = m.end()
    tokens.append(Tok("end", "", len(text)))
    return tokens


class _Parser:
    def __init__(self, text: str):
        self.text = text
        self.toks = tokenize(text)
        self.i = 0

    @property
    def tok(self) -> Tok:
        return self.toks[self.i]

    def accept(self, kind: str, value: str | None = None) -> Tok | None:
        t = self.tok
        if t.kind == kind and (value is None or t.value == value):
            self.i += 1
            return t
        return None

    def expect(self, kind: str, value: str, what: str) -> Tok:
        t = self.accept(kind, value)
        if t is None:
            got = self.tok.value or "end of expression"
            raise ExprError(f"expected {what}, found {got!r}", self.tok.pos)
        return t

    def parse(self) -> Node:
        if self.tok.kind == "end":
            raise ExprError("empty expression", 0)
        node = self.or_()
        if self.tok.kind != "end":
            raise ExprError(f"unexpected {self.tok.value!r}", self.tok.pos)
        return node

    def or_(self) -> Node:
        node = self.and_()
        while self.accept("kw", "or"):
            node = BoolOp("or", node, self.and_())
        return node

    def and_(self) -> Node:
        node = self.not_()
        while self.accept("kw", "and"):
            node = BoolOp("and", node, self.not_())
        return node

    def not_(self) -> Node:
        if self.tok.kind == "kw" and self.tok.value == "not" and not (
                self.toks[self.i + 1].kind == "kw" and self.toks[self.i + 1].value == "in"):
            self.i += 1
            return Not(self.not_())
        return self.compare()

    def compare(self) -> Node:
        left = self.filtered()
        t = self.tok
        if t.kind == "op" and t.value in ("==", "!=", "<", "<=", ">", ">="):
            self.i += 1
            return Compare(t.value, left, self.filtered())
        if t.kind == "kw" and t.value in ("in", "matches"):
            self.i += 1
            return Compare(t.value, left, self.filtered())
        if t.kind == "kw" and t.value == "not" and self.toks[self.i + 1].value == "in":
            self.i += 2
            return Compare("not in", left, self.filtered())
        return left

    def filtered(self) -> Node:
        node = self.unary()
        while self.accept("op", "|"):
            t = self.tok
            if t.kind != "name":
                raise ExprError("expected a filter name after '|'", t.pos)
            self.i += 1
            if t.value not in FILTERS:
                raise ExprError(f"unknown filter '{t.value}' (known: "
                                f"{', '.join(sorted(FILTERS))})", t.pos)
            args: list[Node] = []
            if self.accept("op", "("):
                if not self.accept("op", ")"):
                    args.append(self.or_())
                    while self.accept("op", ","):
                        args.append(self.or_())
                    self.expect("op", ")", "')'")
            lo, hi = FILTERS[t.value][1:]
            if not lo <= len(args) <= hi:
                raise ExprError(f"filter '{t.value}' takes {lo if lo == hi else f'{lo}-{hi}'}"
                                f" argument{'s' if hi != 1 else ''}", t.pos)
            node = Filter(node, t.value, args)
        return node

    def unary(self) -> Node:
        if self.accept("op", "-"):
            return Neg(self.unary())
        return self.postfix()

    def postfix(self) -> Node:
        node = self.primary()
        while True:
            if self.accept("op", "."):
                t = self.tok
                if t.kind not in ("name", "kw"):
                    raise ExprError("expected a name after '.'", t.pos)
                self.i += 1
                node = Attr(node, t.value)
            elif self.accept("op", "["):
                index = self.or_()
                self.expect("op", "]", "']'")
                node = Index(node, index)
            else:
                return node

    def primary(self) -> Node:
        t = self.tok
        if t.kind == "num":
            self.i += 1
            return Literal(float(t.value) if "." in t.value else int(t.value))
        if t.kind == "str":
            self.i += 1
            return Literal(_unescape(t.value[1:-1]))
        if t.kind == "kw" and t.value in ("true", "True"):
            self.i += 1
            return Literal(True)
        if t.kind == "kw" and t.value in ("false", "False"):
            self.i += 1
            return Literal(False)
        if t.kind == "kw" and t.value in ("null", "None"):
            self.i += 1
            return Literal(None)
        if t.kind == "name":
            self.i += 1
            return Name(t.value)
        if self.accept("op", "("):
            node = self.or_()
            self.expect("op", ")", "')'")
            return node
        if self.accept("op", "["):
            items: list[Node] = []
            if not self.accept("op", "]"):
                items.append(self.or_())
                while self.accept("op", ","):
                    items.append(self.or_())
                self.expect("op", "]", "']'")
            return ListLit(items)
        what = t.value or "end of expression"
        raise ExprError(f"expected a value, found {what!r}", t.pos)


def parse_expression(text: str) -> Node:
    return _Parser(text).parse()
