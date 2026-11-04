"""Rule-based announcement classification.

Deterministic and explainable: each result records the rule id and the text
that matched. Unmatched filings fall back to `unclassified` with low
confidence and are flagged for review rather than guessed.

An LLM classifier can be added behind the same interface for the residue the
rules miss; it is deliberately not on the default path (see docs).
"""

from __future__ import annotations

import re

from .models import Announcement, Classification
from .taxonomy import RULES, is_routine

_PREFIX = re.compile(r"^.*?\s-\s\d{6}\s-\s")  # "COMPANY LTD. - 517397 - " on BSE subjects


def classification_text(a: Announcement) -> str:
    subject = _PREFIX.sub("", a.subject)
    parts = [subject, a.headline or "", a.exchange_subcategory or "", a.exchange_category or ""]
    return " | ".join(p for p in parts if p).lower()


def classify(a: Announcement) -> Classification:
    text = classification_text(a)
    for rule in RULES:
        m = rule.match(text)
        if m:
            # A broad "update" match on generic text is only medium confidence.
            conf = "medium" if rule.id in {"pr-generic", "mc-appoint", "pr-launch"} else "high"
            return Classification(
                category=rule.category,
                subtype=rule.subtype,
                routine=is_routine(rule.category, rule.subtype),
                method="rule",
                rule_id=rule.id,
                matched=m.group(0)[:80],
                confidence=conf,
            )
    # Unknown filings are surfaced for review, never buried as routine.
    return Classification(
        category="unclassified",
        subtype="needs_review",
        routine=False,
        method="fallback",
        rule_id=None,
        matched=None,
        confidence="low",
    )
