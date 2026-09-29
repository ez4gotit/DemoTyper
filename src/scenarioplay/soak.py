"""`scenarioplay soak`: run a scenario several times and check that every take succeeds
and follows the same sequence of steps (spec 13 reliability; phase 4 acceptance: 10
consecutive takes from a snapshot)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def step_sequence(report: dict[str, Any]) -> list[tuple[str, str, tuple[str, ...]]]:
    """What "the same sequence of steps" compares: each step's path, status, and the branch
    and loop notes (typo lines and timings vary between takes; they are left out)."""
    keep = ("branch:", "repeat ", "while: pass", "until: pass", "=")
    out = []
    for step in report["steps"]:
        notes = tuple(n for n in step.get("notes", []) if n.startswith(keep)
                      and "typo" not in n)
        out.append((step["path"], step["status"], notes))
    return out


@dataclass
class SoakResult:
    takes: list[Path] = field(default_factory=list)
    codes: list[int] = field(default_factory=list)
    sequences: list[list[Any]] = field(default_factory=list)
    mismatches: list[int] = field(default_factory=list)  # takes differing from the first

    @property
    def ok(self) -> bool:
        return bool(self.codes) and all(c == 0 for c in self.codes) and not self.mismatches

    def summary(self) -> str:
        lines = [f"{len(self.codes)} takes: {sum(1 for c in self.codes if c == 0)} succeeded"]
        for i, (path, code) in enumerate(zip(self.takes, self.codes, strict=True), start=1):
            flag = "" if i - 1 not in self.mismatches else "  <- different steps"
            lines.append(f"  take {i}: exit {code}  {path}{flag}")
        if self.mismatches:
            lines.append("steps differ from take 1 in takes "
                         + ", ".join(str(i + 1) for i in self.mismatches))
        elif self.codes:
            lines.append(f"every take followed the same {len(self.sequences[0])} steps")
        return "\n".join(lines)


def record(result: SoakResult, take_dir: Path, code: int) -> None:
    report = json.loads((take_dir / "report.json").read_text(encoding="utf-8"))
    sequence = step_sequence(report)
    result.takes.append(take_dir)
    result.codes.append(code)
    result.sequences.append(sequence)
    if result.sequences and sequence != result.sequences[0]:
        result.mismatches.append(len(result.sequences) - 1)
