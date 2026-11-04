"""Indian fiscal periods (April-March), as labels and quarter lists.

Labels: "Q2 FY27" (quarter ending 30 Sep 2026), "H1 FY27", "H2 FY27",
"9M FY27", "FY27". Calendar-year reporters are not supported yet.
"""

from __future__ import annotations

import re
from datetime import date

QEND = {1: (6, 30), 2: (9, 30), 3: (12, 31), 4: (3, 31)}


def fy_of(d: date) -> int:
    return d.year + 1 if d.month >= 4 else d.year


def quarter_of(d: date) -> tuple[int, int]:
    """(fiscal year, quarter) containing date d."""
    fy = fy_of(d)
    q = {4: 1, 5: 1, 6: 1, 7: 2, 8: 2, 9: 2, 10: 3, 11: 3, 12: 3, 1: 4, 2: 4, 3: 4}[d.month]
    return fy, q


def qlabel(fy: int, q: int) -> str:
    return f"Q{q} FY{fy % 100:02d}"


def fylabel(fy: int) -> str:
    return f"FY{fy % 100:02d}"


def quarter_end(fy: int, q: int) -> date:
    m, d = QEND[q]
    return date(fy - 1 if q < 4 else fy, m, d)


def label_for_end(d: date, kind: str = "quarter") -> str | None:
    """Label for a period ending on d. kind: quarter | ytd | year."""
    if (d.month, d.day) not in {(6, 30), (9, 30), (12, 31), (3, 31)}:
        return None
    fy, q = quarter_of(d)
    if kind == "quarter":
        return qlabel(fy, q)
    if kind == "year" or q == 4:
        return fylabel(fy)
    return {1: qlabel(fy, 1), 2: f"H1 FY{fy % 100:02d}", 3: f"9M FY{fy % 100:02d}"}[q]


PERIOD = re.compile(r"^(?:(Q[1-4])|(H[12])|(9M))?\s*FY(\d{2})$")


def parse(label: str) -> tuple[str, int] | None:
    """("Q2"|"H1"|"H2"|"9M"|"FY", fiscal year) or None."""
    m = PERIOD.match(label.strip())
    if not m:
        return None
    kind = m.group(1) or m.group(2) or m.group(3) or "FY"
    return kind, 2000 + int(m.group(4))


def quarters(label: str) -> list[str]:
    """Quarter labels that make up a period, in order."""
    p = parse(label)
    if not p:
        return []
    kind, fy = p
    qs = {"Q1": [1], "Q2": [2], "Q3": [3], "Q4": [4], "H1": [1, 2], "H2": [3, 4], "9M": [1, 2, 3], "FY": [1, 2, 3, 4]}[kind]
    return [qlabel(fy, q) for q in qs]


def shift_year(label: str, years: int = -1) -> str:
    """Same period one fiscal year earlier (or later)."""
    p = parse(label)
    if not p:
        return label
    kind, fy = p
    pre = "" if kind == "FY" else kind + " "
    return f"{pre}FY{(fy + years) % 100:02d}"


def q_index(label: str) -> int:
    """Sortable index for a quarter label."""
    p = parse(label)
    assert p and p[0].startswith("Q"), label
    return p[1] * 4 + int(p[0][1])


def from_index(i: int) -> str:
    fy, q = divmod(i - 1, 4)
    return qlabel(fy, q + 1)


def prev_q(label: str, n: int = 1) -> str:
    return from_index(q_index(label) - n)


def end_of(label: str) -> date | None:
    qs = quarters(label)
    if not qs:
        return None
    p = parse(qs[-1])
    assert p
    return quarter_end(p[1], int(p[0][1]))


def sort_key(label: str) -> tuple[int, int]:
    e = end_of(label)
    n = len(quarters(label))
    return ((e.toordinal() if e else 0), n)
