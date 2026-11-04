"""Number formatting shared by explanations and the feed (Indian conventions)."""

from __future__ import annotations


def _group_indian(n: int) -> str:
    s = str(abs(n))
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts) + "," + tail


def cr(v: float, digits: int = 1) -> str:
    sign = "-" if v < 0 else ""
    whole = int(abs(round(v, digits)))
    frac = f"{abs(round(v, digits)) - whole:.{digits}f}"[1:] if digits else ""
    return f"{sign}{_group_indian(whole)}{frac}"


def amount(v: float) -> str:
    """₹ crore amount: no decimals for whole numbers."""
    return cr(v, 0 if float(v).is_integer() else 1)


def pct(v: float | None, digits: int = 1, signed: bool = True) -> str:
    if v is None:
        return "n/a"
    s = f"{v * 100:.{digits}f}%"
    return ("+" + s) if signed and v > 0 else s


def pp(v: float, digits: int = 1) -> str:
    return f"{v:+.{digits}f} pp"
