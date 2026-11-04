"""Shared recorder for FINN evaluation runs: every check is a row with an area, a pass/fail and the evidence."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"


@dataclass
class Check:
    area: str          # A..E
    group: str         # e.g. "A1 values vs PDF"
    name: str
    passed: bool
    detail: str = ""
    severity: str = "normal"   # critical | normal | info
    data: dict[str, Any] = field(default_factory=dict)


class Recorder:
    def __init__(self, suite: str):
        self.suite = suite
        self.checks: list[Check] = []
        self.metrics: dict[str, Any] = {}
        self.t0 = time.time()

    def check(self, area, group, name, passed, detail="", severity="normal", **data):
        self.checks.append(Check(area, group, name, bool(passed), str(detail)[:600], severity, data))
        return bool(passed)

    def metric(self, key, value):
        self.metrics[key] = value

    def save(self, label: str) -> Path:
        RESULTS.mkdir(parents=True, exist_ok=True)
        p = RESULTS / f"{self.suite}_{label}.json"
        groups: dict[str, dict[str, int]] = {}
        for c in self.checks:
            g = groups.setdefault(c.group, {"passed": 0, "failed": 0})
            g["passed" if c.passed else "failed"] += 1
        p.write_text(json.dumps({"suite": self.suite, "label": label, "seconds": round(time.time() - self.t0, 1), "metrics": self.metrics,
                                 "groups": groups, "checks": [asdict(c) for c in self.checks]}, indent=1, default=str))
        return p

    def summary(self) -> str:
        lines = []
        groups: dict[str, list[Check]] = {}
        for c in self.checks:
            groups.setdefault(c.group, []).append(c)
        for g, cs in groups.items():
            bad = [c for c in cs if not c.passed]
            lines.append(f"{g:<48} {len(cs) - len(bad):>4}/{len(cs):<4}" + (f"  FAIL: {', '.join(c.name for c in bad[:6])}{' …' if len(bad) > 6 else ''}" if bad else ""))
        for k, v in self.metrics.items():
            lines.append(f"  metric {k}: {v}")
        return "\n".join(lines)
