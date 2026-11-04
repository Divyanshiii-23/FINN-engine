"""Duplicate handling and event clustering.

Three kinds of sameness, handled differently:
1. Exact repeat: the same filing posted twice on one exchange (same attachment,
   same subject). The later copy is marked a duplicate.
2. Cross-exchange copy: the same filing on BSE and NSE (similar text, close in
   time). One canonical copy is kept; the other's reference is retained.
3. Revision: a "revised"/"corrigendum" filing is NOT a duplicate. It is kept
   and linked to the filing it supersedes.

Distinct but related filings (results + presentation + press release on the
same evening) are then clustered into one event.
"""

from __future__ import annotations

import hashlib
import re
from datetime import timedelta

from .classify import classification_text
from .models import Announcement, Classification
from .taxonomy import prior

_PREFIX = re.compile(r"^.*?\s-\s\d{6}\s-\s")
_REVISION = re.compile(r"\b(revis(ed|ion)|corrigendum|addendum|erratum|correction to)\b", re.I)
CROSS_LAG = timedelta(hours=6)
_STOPWORDS = {"the", "of", "and", "for", "to", "in", "on", "a", "an", "under", "regulation", "reg", "sebi", "lodr", "disclosure", "intimation", "with", "by", "is", "as", "at", "ltd", "limited"}


def norm_subject(s: str) -> str:
    s = _PREFIX.sub("", s or "").lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def tokens(a: Announcement) -> set[str]:
    text = norm_subject(a.subject) + " " + norm_subject(a.headline or "")
    return {t for t in text.split() if t not in _STOPWORDS and len(t) > 2}


def jaccard(x: set[str], y: set[str]) -> float:
    return len(x & y) / len(x | y) if x and y else 0.0


def overlap(x: set[str], y: set[str]) -> float:
    return len(x & y) / min(len(x), len(y)) if x and y else 0.0


def _attachment_key(a: Announcement) -> str | None:
    url = a.source.attachment_url
    return url.rsplit("/", 1)[-1].lower() if url else None


def dedupe(items: list[Announcement], cross_window: timedelta = timedelta(minutes=45)) -> list[Announcement]:
    """Mark duplicates in place; returns all items (duplicates included, flagged)."""
    by_id: dict[str, Announcement] = {}
    for a in items:
        by_id.setdefault(a.id, a)  # same source id fetched twice: keep one
    ordered = sorted(by_id.values(), key=lambda a: (a.symbol, a.filed_at, a.source.source != "bse"))
    canon: list[Announcement] = []
    for a in ordered:
        is_rev = bool(_REVISION.search(a.subject) or _REVISION.search(a.headline or ""))
        match: Announcement | None = None
        reason = None
        if is_rev:
            # A revision supersedes the most similar earlier filing from the same company (within 7 days).
            # Overlap coefficient, because a corrigendum shares few words with the original;
            # on ties prefer an earlier filing that carries the document itself.
            pool = [c for c in canon if c.symbol == a.symbol and timedelta(0) <= a.filed_at - c.filed_at <= timedelta(days=7) and not _REVISION.search(c.subject)]
            best = max(pool, key=lambda c: (overlap(tokens(a), tokens(c)), bool(c.source.attachment_url)), default=None)
            if best is not None and overlap(tokens(a), tokens(best)) >= 0.25:
                a.supersedes = best.id
            canon.append(a)
            continue
        for c in reversed(canon):
            if c.symbol != a.symbol:
                continue
            if a.filed_at - c.filed_at > timedelta(days=7):
                break
            same_src = c.source.source == a.source.source
            sim = jaccard(tokens(a), tokens(c))
            if same_src and _attachment_key(a) and _attachment_key(a) == _attachment_key(c):
                match, reason = c, "same attachment posted again"
                break
            # Generic subjects ("Announcement under Regulation 30 (LODR)-General") repeat across unrelated
            # filings, so identical text only counts when the documents can't be told apart.
            ka, kc = _attachment_key(a), _attachment_key(c)
            different_docs = (ka and kc and ka != kc) or (a.attachment_size and c.attachment_size and a.attachment_size != c.attachment_size)
            if same_src and not different_docs and norm_subject(a.subject) == norm_subject(c.subject) and (a.headline or "") == (c.headline or "") and a.filed_at - c.filed_at <= cross_window:
                match, reason = c, "identical subject and headline re-posted"
                break
            # The two exchanges can disseminate the same filing hours apart; near-identical text or an equal
            # file size is strong enough to match across a wider window than loose similarity.
            gap = abs(a.filed_at - c.filed_at)
            same_size = bool(a.attachment_size and a.attachment_size == c.attachment_size)
            if not same_src and ((gap <= cross_window and (sim >= 0.5 or same_size)) or (gap <= CROSS_LAG and (sim >= 0.8 or same_size))):
                match, reason = c, f"same filing on {a.source.source.upper()} and {c.source.source.upper()} (text similarity {sim:.2f}, {int(gap.total_seconds() // 60)} min apart)"
                break
        if match:
            a.duplicate_of = match.id
            a.duplicate_reason = reason
            match.duplicates.append(a.id)
        else:
            canon.append(a)
    return ordered


CLUSTER_WINDOW = timedelta(hours=36)
NO_CLUSTER = {"unclassified", "investor_meetings", "postal_ballot", "agm_egm"}


def cluster(items: list[tuple[Announcement, Classification]]) -> list[list[tuple[Announcement, Classification]]]:
    """Group non-duplicate announcements into events.

    Same company, same category, within 36 hours of the group's first filing.
    Routine categories are not clustered: each filing stands alone.
    """
    live = sorted([x for x in items if not x[0].duplicate_of], key=lambda x: (x[0].symbol, x[0].filed_at))
    groups: list[list[tuple[Announcement, Classification]]] = []
    open_group: dict[tuple[str, str], list[tuple[Announcement, Classification]]] = {}
    for a, c in live:
        key = (a.symbol, c.category)
        g = open_group.get(key)
        if c.category not in NO_CLUSTER and g and a.filed_at - g[0][0].filed_at <= CLUSTER_WINDOW:
            g.append((a, c))
            continue
        g = [(a, c)]
        groups.append(g)
        open_group[key] = g
    return groups


def primary(group: list[tuple[Announcement, Classification]]) -> tuple[Announcement, Classification]:
    """The filing that defines the event: the most important subtype, earliest on ties."""
    return max(group, key=lambda x: (prior(x[1].category, x[1].subtype), -x[0].filed_at.timestamp()))


def event_id(group: list[tuple[Announcement, Classification]]) -> str:
    return hashlib.sha1("|".join(sorted(a.id for a, _ in group)).encode()).hexdigest()[:16]


__all__ = ["dedupe", "cluster", "primary", "event_id", "norm_subject", "classification_text"]
