"""The wiki's generated reference pages are current and complete (spec 14.3)."""

from __future__ import annotations

from ruamel.yaml import YAML

from scenarioplay.docsgen import generate
from scenarioplay.loader import load_scenario
from scenarioplay.plugins import ACTIONS, CONDITIONS, load_plugins

from ..conftest import ROOT

DOCS = ROOT / "docs"


def test_generated_reference_is_current():
    """Regenerate with: scenarioplay gen-docs"""
    for path, text in generate(DOCS).items():
        assert path.exists(), f"missing {path.name}: run `scenarioplay gen-docs`"
        assert path.read_text(encoding="utf-8") == text, f"{path.name} is stale"


def test_every_keyword_has_two_examples_and_a_main_description():
    load_plugins()
    data = YAML(typ="safe").load((DOCS / "reference.yaml").read_text(encoding="utf-8"))
    for keyword in ACTIONS:
        entry = data["actions"].get(keyword, {})
        assert len(entry.get("examples", [])) >= 2, f"{keyword}: needs two examples"
        assert data["main"].get(keyword), f"{keyword}: needs a `main` description"
    for keyword in CONDITIONS:
        assert data["conditions"].get(keyword, {}).get("examples"), keyword


def test_reference_examples_are_valid_steps(write_scenario):
    """Every example parses as steps (in a scenario that declares what they use)."""
    data = YAML(typ="safe").load((DOCS / "reference.yaml").read_text(encoding="utf-8"))
    for keyword, entry in data["actions"].items():
        if keyword == "include":
            continue  # its examples name files that exist only in a real project
        for i, example in enumerate(entry.get("examples", [])):
            if example.lstrip().startswith(("setup:", "#")) and "setup:" in example:
                continue  # a section excerpt, not a step list
            body = "\n".join("  " + line for line in example.splitlines()
                             if not line.startswith("#"))
            defines = "" if keyword == "define" else DEFINES
            scenario = PRELUDE + "steps:\n" + defines + body + "\n"
            _, problems = load_scenario(write_scenario(scenario, f"{keyword}{i}.yaml"))
            errors = [p.format() for p in problems if p.severity == "error"]
            assert not errors, f"{keyword} example {i + 1}: {errors}"


DEFINES = """\
  - define: create_user
    params: [name]
    steps: [{run: "echo {{ name }}"}]
"""

PRELUDE = """\
target: {kind: vmware, vmx: /vms/lab.vmx, snapshot: clean, record: host}
defaults:
  buffers: {pubkey: "ssh-ed25519 AAAA... user@host", token: "abc"}
layout: grid
consoles:
  - {name: main}
  - {name: server}
  - {name: client}
  - {name: logs}
  - {name: a}
  - {name: b}
  - {name: extra, start: false}
vars:
  packages: [nginx]
  base_packages: [curl]
  env_name: dev
  attempts: 2
  hosts: [a]
  online: true
  keep_logs: false
  version: "1.2"
  count: "0"
  status: ready
  state: active
  used: "10"
  who: x
"""
