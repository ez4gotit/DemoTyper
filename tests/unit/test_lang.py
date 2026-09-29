from __future__ import annotations

import pytest

from scenarioplay.lang import ExprError, LiveMapping, Scope, parse_expression, parse_template


def scope(**values):
    last = {"exit_code": 0, "output": "ok", "matched": "need_password"}
    return Scope({"env": {"HOME": "/home/u"}, "last": LiveMapping(lambda: last),
                  "secret": {"PW": "hunter2"}}, [dict(values), {}])


def ev(text, **values):
    return parse_expression(text).eval(scope(**values))


@pytest.mark.parametrize("text,expected", [
    ("1 == 1", True), ("'a' != 'b'", True), ("2 < 3 and 3 <= 3", True),
    ("not false", True), ("1 > 2 or 2 > 1", True), ("(1 < 2) == true", True),
    ("'ng' in 'nginx'", True), ("'x' not in ['a', 'b']", True),
    ("'nginx/1.24' matches '^nginx/\\d+'", True), ("-3 < 0", True),
    ("null == None", True), ("[1, 2][1]", 2), ("1.5 >= 1", True),
])
def test_literals_and_operators(text, expected):
    assert ev(text) == expected


def test_names_attrs_and_builtins():
    assert ev("site", site="example.local") == "example.local"
    assert ev("last.matched == 'need_password'") is True
    assert ev("last.exit_code == 0") is True
    assert ev("env.HOME") == "/home/u"
    assert ev("cfg.port", cfg={"port": 80}) == 80
    assert ev("pkgs[0]", pkgs=["nginx"]) == "nginx"


def test_filters():
    assert ev("pkgs | join(' ')", pkgs=["nginx", "curl"]) == "nginx curl"
    assert ev("name | upper", name="x") == "X"
    assert ev("'  a ' | trim") == "a"
    assert ev("missing | default('d')") == "d"
    assert ev("missing.deep | default(3)") == 3
    assert ev("pkgs | length", pkgs=[1, 2, 3]) == 3
    assert ev("n | int > 2", n="3") is True


@pytest.mark.parametrize("text,fragment", [
    ("nope == 1", "undefined variable 'nope'"),
    ("n > 2", "use `| int`"),
    ("1 +", "unexpected character"),
    ("x | frobnicate", "unknown filter 'frobnicate'"),
    ("(1 == 1", "expected ')'"),
    ("", "empty expression"),
    ("'a' matches '(['", "invalid regular expression"),
])
def test_errors_are_explained(text, fragment):
    with pytest.raises(ExprError, match=None) as e:
        ev(text, n="3", x="y")
    assert fragment in str(e.value)


def test_no_python_attribute_access():
    with pytest.raises(ExprError):
        ev("s.upper", s="abc")
    with pytest.raises(ExprError):
        ev("s.__class__", s="abc")


def test_template_text_and_native():
    t = parse_template("sudo apt install -y {{ packages | join(' ') }}")
    assert t.render(scope(packages=["nginx", "curl"])) == "sudo apt install -y nginx curl"
    assert parse_template("{{ packages }}").render(scope(packages=[1, 2]), native=True) == [1, 2]
    assert parse_template("n={{ n }}").render(scope(n=True)) == "n=true"
    assert parse_template("plain").is_static


def test_template_names_and_paths():
    t = parse_template("{{ a }} {{ b | default(c) }} {{ secret.PW }} {{ loop.index }}")
    assert t.names() == {"a", "b", "c", "secret", "loop"}
    assert "secret.PW" in t.paths()


def test_template_errors_have_position():
    with pytest.raises(ExprError) as e:
        parse_template("echo {{ oops")
    assert e.value.pos == 5
    with pytest.raises(ExprError):
        parse_template("{{ 1 + }}")


def test_scope_layers_and_set():
    s = Scope({}, [{"a": "file"}, {"a": "cli"}, {}])
    assert s.lookup("a") == "cli"
    s.push({"item": 1})
    s.set("item", 2)          # updates the loop variable
    s.set("found", "x")       # goes to the runtime layer
    assert s.lookup("item") == 2
    s.pop()
    assert s.lookup("found") == "x"
    assert s.snapshot() == {"a": "cli", "found": "x"}
