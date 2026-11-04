"""Prints per-group pass rates for each recorded run, side by side, from eval/results/*.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

R = Path(__file__).resolve().parent / "results"


def load(name):
    p = R / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else None


def groups(run):
    out = {}
    for c in run["checks"]:
        g = out.setdefault(c["group"], [0, 0, 0])
        g[0] += c["passed"]
        g[1] += 1
        g[2] += (not c["passed"]) and c["severity"] == "critical"
    return out


def main(runs):
    data = {r: load(r) for r in runs}
    allg = []
    for r in runs:
        if data[r]:
            for g in groups(data[r]):
                if g not in allg:
                    allg.append(g)
    print("| Group | " + " | ".join(runs) + " |")
    print("|---|" + "---|" * len(runs))
    for g in sorted(allg):
        cells = []
        for r in runs:
            gg = groups(data[r]).get(g) if data[r] else None
            cells.append(f"{gg[0]}/{gg[1]}" + (f" ({gg[2]} crit)" if gg[2] else "") if gg else "–")
        print(f"| {g} | " + " | ".join(cells) + " |")
    for r in runs:
        if data[r]:
            cs = data[r]["checks"]
            print(f"\n{r}: {sum(c['passed'] for c in cs)}/{len(cs)} passed, {sum((not c['passed']) and c['severity'] == 'critical' for c in cs)} critical failures")
            for k, v in (data[r].get("metrics") or {}).items():
                print(f"  {k}: {v}")


if __name__ == "__main__":
    main(sys.argv[1:] or ["engine_baseline", "engine_after_fixes_round1", "engine_after_fixes"])
