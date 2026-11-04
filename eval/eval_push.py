"""C. Push intelligence.

C1 classification: held-out announcements (gold file) and the fixture feed
C2 materiality prioritisation: tier agreement, critical recall, routine noise, pairwise ordering
C3 duplicate detection: constructed scenarios through FINN's dedupe + clustering
C5 EOD volume/price anomaly detection: synthetic price series through market.signal_at, and the fixture feed
(C4 alert thresholds runs in TypeScript against the web app's own computeAlerts: alerts_eval.ts)
"""

from __future__ import annotations

import hashlib
import json
import random
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))

from finn_engine.classify import classify  # noqa: E402
from finn_engine.dedupe import cluster, dedupe  # noqa: E402
from finn_engine.extract.facts import extract_facts  # noqa: E402
from finn_engine.market import signal_at  # noqa: E402
from finn_engine.materiality import score  # noqa: E402
from finn_engine.models import Announcement, Company, EodBar, SourceRef  # noqa: E402

GOLD = Path(__file__).resolve().parent / "gold"
IST = timezone(timedelta(hours=5, minutes=30))
T0 = datetime(2026, 11, 3, 18, 0, tzinfo=IST)


def ann(subject, headline=None, subcat=None, at=T0, source="bse", attachment=None, size=None, symbol="EVALCO", name="EVALCO INDUSTRIES LTD", sid=None) -> Announcement:
    sid = sid or hashlib.sha1(f"{source}{subject}{headline}{at}{attachment}{random.random()}".encode()).hexdigest()[:12]
    return Announcement(id=hashlib.sha1(f"{source}:{sid}".encode()).hexdigest()[:16], symbol=symbol, company_on_filing=name, subject=subject, headline=headline,
                        exchange_subcategory=subcat, filed_at=at, attachment_size=size,
                        source=SourceRef(source=source, source_id=sid, attachment_url=(f"https://www.bseindia.com/xml-data/corpfiling/AttachLive/{attachment}" if attachment else None),
                                         fetched_at=datetime.now(timezone.utc), fixture=True))


TIER_RANK = {"routine": 0, "brief": 1, "interrupt": 2}


def run(rec, feed: dict) -> None:
    held_out(rec, "announcements.json", "set 1")
    held_out(rec, "announcements_v2.json", "set 2, unseen")
    fixture_feed(rec, feed)
    duplicates(rec)
    eod(rec, feed)


def held_out(rec, fname: str, tag: str) -> None:
    g = json.loads((GOLD / fname).read_text())
    k = "1" if tag == "set 1" else "2"
    co = Company(symbol="EVALCO", name="EVALCO INDUSTRIES LTD", market_cap_cr=g["company"]["market_cap_cr"], revenue_ttm_cr=g["company"]["revenue_ttm_cr"])
    rows = []
    for it in g["items"]:
        a = ann(f"EVALCO INDUSTRIES LTD - 990199 - {it['subject']}", it["headline"], it["subcat"])
        c = classify(a)
        facts = extract_facts(c.category, c.subtype, " ".join(filter(None, [a.subject, a.headline])))
        m = score(co, c, facts, None, None, False)
        rows.append((it, c, m))
        rec.check("C", f"C1 classification (held-out {tag})", f"{it['id']} {it['subject'][:60]}", c.category in it["cat"],
                  f"got {c.category}/{c.subtype} ({c.method}); gold {it['cat']}", severity="critical" if it.get("critical") else "normal")
        rec.check("C", f"C2 materiality tier (held-out {tag})", f"{it['id']} {it['subject'][:60]}", m.tier in it["tier"],
                  f"got {m.tier} ({m.score}); gold {it['tier']}; {'; '.join(x.detail for x in m.components)[:200]}", severity="critical" if it.get("critical") else "normal")
    n = len(rows)
    acc = sum(c.category in it["cat"] for it, c, _ in rows)
    tier = sum(m.tier in it["tier"] for it, _, m in rows)
    crit = [(it, m) for it, _, m in rows if it.get("critical")]
    crit_hit = sum(m.tier == "interrupt" for _, m in crit)
    crit_brief = sum(m.tier in ("interrupt", "brief") for _, m in crit)
    routine = [(it, m) for it, _, m in rows if it["tier"] == ["routine"]]
    noise = [it["id"] for it, m in routine if m.tier == "interrupt"]
    pairs = [(a, b) for a in crit for b in routine]
    ordered = sum(a[1].score > b[1].score for a, b in pairs)
    rec.metric(f"C1_category_accuracy_set{k}", f"{acc}/{n} ({acc / n:.0%})")
    rec.metric(f"C1_fallback_unclassified_set{k}", sum(c.method == "fallback" for _, c, _ in rows))
    rec.metric(f"C2_tier_agreement_set{k}", f"{tier}/{n} ({tier / n:.0%})")
    rec.metric(f"C2_critical_recall_interrupt_set{k}", f"{crit_hit}/{len(crit)}")
    rec.metric(f"C2_critical_recall_brief_or_interrupt_set{k}", f"{crit_brief}/{len(crit)}")
    rec.metric(f"C2_routine_items_raised_to_interrupt_set{k}", noise)
    rec.metric(f"C2_pairwise_critical_above_routine_set{k}", f"{ordered}/{len(pairs)} ({ordered / max(1, len(pairs)):.1%})")


# ------------------------------------------------------------------ the actual fixture feed

FEED_GOLD = [  # symbol, subject fragment, categories, tiers
    ("KESTREL", "Outcome of Board Meeting", ["results"], ["brief", "interrupt"]),
    ("KESTREL", "Newspaper Publication", ["unclassified", "results"], ["routine", "brief", "interrupt"]),
    ("SARANG", "Credit Rating", ["credit_rating"], ["interrupt"]),
    ("TIDEMARK", "Resignation of Chief Financial Officer", ["management_change"], ["interrupt"]),
    ("VEDIKA", "Warning Letter", ["litigation"], ["interrupt"]),
    ("VEDIKA", "Intimation of Earnings Call", ["earnings_call"], ["routine"]),
    ("VEDIKA", "ESG Report", ["unclassified"], ["routine"]),
    ("CORAL", "Encumbrance", ["pledging"], ["brief", "interrupt"]),
    ("CORAL", "Loss of Share Certificate", ["unclassified"], ["routine"]),
    ("KAVERI", "Capacity Expansion", ["capex"], ["brief", "interrupt"]),
    ("HALCYON", "Insider Trading", ["insider_trading"], ["routine", "brief"]),
    ("HALCYON", "Regulation 74(5)", ["unclassified"], ["routine"]),
    ("AURELIA", "Interim Dividend", ["dividend"], ["routine", "brief"]),
    ("AURELIA", "Analyst / Institutional", ["investor_meetings"], ["routine"]),
    ("QUANTA", "Order Win", ["press_release"], ["brief", "interrupt"]),
    ("QUANTA", "ESOP", ["unclassified"], ["routine"]),
    ("LOTUS", "Financial Results", ["results"], ["brief", "interrupt"]),
    ("LOTUS", "Transcript", ["earnings_call"], ["routine"]),
    ("HELIX", "Acquisition", ["mna"], ["brief", "interrupt"]),
    ("HELIX", "Audio Recording", ["earnings_call"], ["routine"]),
    ("ORBIT", "Extra-ordinary General Meeting", ["agm_egm"], ["routine"]),
    ("MONSOON", "Tax Demand", ["litigation"], ["routine", "brief"]),
    ("MONSOON", "Postal Ballot", ["postal_ballot"], ["routine"]),
    ("ANVIL", "Fund Raising", ["fund_raise"], ["brief", "interrupt"]),
    ("ANVIL", "Trading Window", ["unclassified"], ["routine"]),
    ("NGRID", "Independent Director", ["management_change"], ["routine", "brief"]),
    ("NGRID", "website", ["unclassified"], ["routine"]),
    ("MERIDIAN", "40(9)", ["unclassified"], ["routine"]),
]


def fixture_feed(rec, feed: dict) -> None:
    for sym, frag, cats, tiers in FEED_GOLD:
        ev = [e for e in feed["events"] if e["symbol"] == sym and any(frag.lower() in a["subject"].lower() for a in e["announcements"])]
        if not ev:
            rec.check("C", "C1 classification (fixture feed)", f"{sym} {frag}", False, "no event in the feed", severity="critical")
            continue
        e = ev[0]
        rec.check("C", "C1 classification (fixture feed)", f"{sym} {frag}", e["category"] in cats, f"got {e['category']}/{e['subtype']}")
        rec.check("C", "C2 materiality tier (fixture feed)", f"{sym} {frag}", e["materiality"]["tier"] in tiers, f"got {e['materiality']['tier']} ({e['materiality']['score']})")
    # Ordering within the brief: every interrupt event outranks every routine one
    evs = feed["events"]
    ints = [e["materiality"]["score"] for e in evs if e["materiality"]["tier"] == "interrupt"]
    rout = [e["materiality"]["score"] for e in evs if e["materiality"]["tier"] == "routine"]
    rec.check("C", "C2 materiality tier (fixture feed)", "tiers are consistent with scores (min interrupt > max routine)", not ints or not rout or min(ints) > max(rout), f"{min(ints or [0])} vs {max(rout or [0])}")
    rej = [r for r in feed.get("rejections", []) if "TIDEMARK" in json.dumps(r) or "SOME OTHER COMPANY" in json.dumps(r)]
    rec.check("C", "C1 classification (fixture feed)", "filing from a mismatched filer is rejected, not classified", bool(rej), json.dumps(rej[:1])[:200], severity="critical")
    # Duplicates in the real feed
    # The board-meeting notice a week earlier is its own event; the results evening (3 Nov onwards) must be one.
    k = [e for e in evs if e["symbol"] == "KESTREL" and e["category"] == "results" and e["first_filed_at"] >= "2026-11-03"]
    anns = [a for e in k for a in e["announcements"]]
    dups = [a for a in anns if a.get("duplicate_of")]
    corr = [a for a in anns if "corrigendum" in a["subject"].lower()]
    rec.check("C", "C3 duplicate detection (fixture feed)", "KESTREL results posted twice: second copy marked duplicate", len([a for a in dups if "Financial Results for the Quarter" in a["subject"]]) >= 1, f"{len(dups)} duplicates")
    rec.check("C", "C3 duplicate detection (fixture feed)", "KESTREL corrigendum kept and linked, not a duplicate", bool(corr) and all(not a.get("duplicate_of") and a.get("supersedes") for a in corr), str([(a['subject'][-40:], a.get('duplicate_of'), a.get('supersedes')) for a in corr]))
    rec.check("C", "C3 duplicate detection (fixture feed)", "KESTREL results, outcome, press release and deck form one event", len(k) == 1, f"{len(k)} results events")
    nse = [a for e in evs for a in e["announcements"] if a["source"]["source"] == "nse"]
    rec.check("C", "C3 duplicate detection (fixture feed)", "NSE copies are folded into the BSE filing", all(a.get("duplicate_of") for a in nse), f"{len(nse)} NSE rows; {sum(1 for a in nse if not a.get('duplicate_of'))} standing alone")


# ------------------------------------------------------------------ C3 constructed scenarios

def duplicates(rec) -> None:
    S = []  # (name, announcements, expectation fn)
    t = T0
    a1 = ann("EVALCO INDUSTRIES LTD - 990199 - Outcome of Board Meeting", "Board approved the unaudited results for the quarter ended 30 September 2026", at=t, attachment="X1.pdf", size=1000)
    a2 = ann("Outcome of Board Meeting", "Board approved the unaudited results for the quarter ended 30 September 2026", at=t + timedelta(minutes=4), source="nse", size=1000)
    S.append(("BSE and NSE copies 4 minutes apart", [a1, a2], lambda xs: xs[1].duplicate_of == xs[0].id, True))
    b1 = ann("Outcome of Board Meeting", "Board approved the unaudited results for the quarter ended 30 September 2026", at=t, attachment="X2.pdf")
    b2 = ann("Outcome of Board Meeting", "Board approved the unaudited results for the quarter ended 30 September 2026", at=t + timedelta(hours=2, minutes=10), source="nse")
    S.append(("BSE and NSE copies 2h10m apart (exchange lag)", [b1, b2], lambda xs: xs[1].duplicate_of == xs[0].id, True))
    c1 = ann("Financial Results for the Quarter Ended 30 September 2026", "Unaudited results", at=t, attachment="R.pdf", size=5000)
    c2 = ann("Financial Results for the Quarter Ended 30 September 2026", "Unaudited results", at=t + timedelta(minutes=1), attachment="R.pdf", size=5000)
    S.append(("same attachment re-posted on BSE", [c1, c2], lambda xs: xs[1].duplicate_of == xs[0].id, True))
    d1 = ann("Financial Results for the Quarter Ended 30 September 2026", "Unaudited results", at=t, attachment="R3.pdf")
    d2 = ann("Corrigendum to Financial Results", "Correction of a typographical error in note 4", at=t + timedelta(hours=3))
    S.append(("corrigendum supersedes, not duplicate", [d1, d2], lambda xs: xs[1].duplicate_of is None and xs[1].supersedes == xs[0].id, True))
    e1 = ann("Financial Results for the Quarter Ended 30 June 2026", "Unaudited results for the quarter ended 30.06.2026", at=t - timedelta(days=95), attachment="Q1.pdf")
    e2 = ann("Financial Results for the Quarter Ended 30 September 2026", "Unaudited results for the quarter ended 30.09.2026", at=t, attachment="Q2.pdf")
    S.append(("two quarters' results are not duplicates", [e1, e2], lambda xs: xs[0].duplicate_of is None and xs[1].duplicate_of is None, True))
    f1 = ann("Announcement under Regulation 30 (LODR)-General", None, "General", at=t, attachment="G1.pdf", size=1111)
    f2 = ann("Announcement under Regulation 30 (LODR)-General", None, "General", at=t + timedelta(minutes=12), attachment="G2.pdf", size=2222)
    S.append(("two different 'General' filings with the same subject and different attachments", [f1, f2], lambda xs: xs[1].duplicate_of is None, True))
    g1 = ann("Resignation of Chief Financial Officer", "Mr. S. Kulkarni has resigned as Chief Financial Officer", at=t)
    g2 = ann("Appointment of Chief Financial Officer", "Ms. R. Menon appointed as Chief Financial Officer", at=t + timedelta(minutes=7), source="nse")
    S.append(("CFO resignation (BSE) and appointment (NSE) are different filings", [g1, g2], lambda xs: xs[1].duplicate_of is None, True))
    h1 = ann("Outcome of Board Meeting", "Board approved the results", at=t, symbol="EVALCO")
    h2 = ann("Outcome of Board Meeting", "Board approved the results", at=t + timedelta(minutes=1), symbol="OTHERCO", name="OTHERCO LTD")
    S.append(("same text from two companies is not a duplicate", [h1, h2], lambda xs: xs[0].duplicate_of is None and xs[1].duplicate_of is None, True))
    i1 = ann("Intimation of Record Date for Dividend", "Record date 20 November 2026 for an interim dividend of Rs. 4 per share", at=t)
    i2 = ann("INTIMATION OF RECORD DATE FOR DIVIDEND.", "Record date 20 November 2026 for an interim dividend of Rs. 4 per share.", at=t + timedelta(minutes=9), source="nse")
    S.append(("case and punctuation differences across exchanges", [i1, i2], lambda xs: xs[1].duplicate_of == xs[0].id, True))
    j1 = ann("Intimation of Record Date for Dividend", "Record date 20 November 2026 for an interim dividend of Rs. 4 per share", at=t)
    j2 = ann("Intimation of Record Date for Dividend", "Record date 20 November 2026 for an interim dividend of Rs. 4 per share", at=t, sid="same")
    j3 = j2.model_copy()
    S.append(("the same exchange row fetched twice (same id)", [j1, j2, j3], lambda xs: len(xs) == 2, True))
    for name, xs, ok, _ in S:
        out = dedupe([x.model_copy(deep=True) for x in xs])
        by = {a.id: a for a in out}
        ordered = [by[x.id] for x in xs if x.id in by] if name != "the same exchange row fetched twice (same id)" else out
        try:
            good = ok(ordered)
        except Exception as e:  # noqa: BLE001
            good = False
        rec.check("C", "C3 duplicate detection (constructed)", name, good, str([(a.source.source, a.subject[:40], a.duplicate_of, a.supersedes, a.duplicate_reason) for a in ordered])[:300], severity="critical")
    # Clustering: results + presentation + press release same evening = one event; a dividend the same evening is separate
    xs = [ann("Outcome of Board Meeting", "Board approved the unaudited results", at=t), ann("Investor Presentation", "Investor presentation for Q2 FY27", at=t + timedelta(minutes=30)),
          ann("Press Release", "Press release on financial results", at=t + timedelta(minutes=40)), ann("Intimation of Record Date for Interim Dividend", "Interim dividend of Rs. 3", at=t + timedelta(minutes=20))]
    groups = cluster([(a, classify(a)) for a in dedupe(xs)])
    sizes = sorted(len(g) for g in groups)
    rec.check("C", "C3 duplicate detection (constructed)", "results evening clusters into one event; dividend stays separate", sizes == [1, 3], f"group sizes {sizes}: " + str([[x[1].category for x in g] for g in groups]))


# ------------------------------------------------------------------ C5 EOD anomalies

def _bars(n=80, vol=1_000_000, last_vol=None, last_ret=0.0, zero_days=(), split_at=None, seed=7, missing_vol=()):
    rnd = random.Random(seed)
    d = date(2026, 6, 1)
    out, px = [], 100.0
    i = 0
    while len(out) < n:
        if d.weekday() < 5:
            r = rnd.gauss(0, 0.012)
            if len(out) == n - 1:
                r = last_ret
            px *= 1 + r
            v = int(vol * rnd.uniform(0.85, 1.15))
            if split_at is not None and len(out) >= split_at:
                v *= 2  # 1:2 split doubles share count and traded volume
            if len(out) in zero_days:
                v = 0
            if len(out) == n - 1 and last_vol is not None:
                v = last_vol
            out.append(EodBar(date=d, open=px, high=px, low=px, close=px, adj_close=px, volume=None if len(out) in missing_vol else v))
            i += 1
        d += timedelta(days=1)
    return out


def eod(rec, feed: dict) -> None:
    cases = []
    b = _bars(last_vol=3_000_000)
    s = signal_at("X", b, set())
    cases.append(("3x volume spike detected", s.vol_ratio_20d is not None and 2.6 <= s.vol_ratio_20d <= 3.5, f"ratio {s.vol_ratio_20d}"))
    b = _bars(last_vol=1_050_000)
    s = signal_at("X", b, set())
    cases.append(("normal volume not flagged (ratio < 2)", s.vol_ratio_20d is not None and s.vol_ratio_20d < 1.5, f"ratio {s.vol_ratio_20d}"))
    b = _bars(n=12, last_vol=5_000_000)
    s = signal_at("X", b, set())
    cases.append(("12 sessions of history: no volume baseline, says so", s.vol_ratio_20d is None and "15 prior" in (s.note or ""), f"ratio {s.vol_ratio_20d} note {s.note}"))
    b = _bars(last_vol=2_200_000, zero_days=tuple(range(62, 72)))
    s = signal_at("X", b, set())
    cases.append(("suspension days (zero volume) in the baseline don't inflate a 2.2x day into a large spike",
                  (s.vol_ratio_20d is None and "with trading" in (s.note or "")) or (s.vol_ratio_20d is not None and s.vol_ratio_20d < 3.0),
                  f"ratio {s.vol_ratio_20d} (baseline {s.avg_vol_20d}); note {s.note}"))
    b = _bars(last_vol=2_200_000, zero_days=(70, 72))
    s = signal_at("X", b, set())
    cases.append(("two suspension days in the window: 2.2x day measured against traded sessions only (about 2.2x)", s.vol_ratio_20d is not None and 1.9 <= s.vol_ratio_20d <= 2.5,
                  f"ratio {s.vol_ratio_20d}"))
    b = _bars(last_vol=0)
    s = signal_at("X", b, set())
    cases.append(("zero volume on the day: ratio 0, no spike", s.vol_ratio_20d == 0, f"ratio {s.vol_ratio_20d}"))
    b = _bars(missing_vol=(79,))
    s = signal_at("X", b, set())
    cases.append(("missing volume on the day: no ratio, no crash", s.vol_ratio_20d is None, f"ratio {s.vol_ratio_20d}"))
    b = _bars(split_at=70)
    s = signal_at("X", b, {b[70].date})
    cases.append(("1:2 split 10 sessions ago: post-split volume is not reported as a spike", (s.vol_ratio_20d is None and "split" in (s.note or "")) or (s.vol_ratio_20d is not None and s.vol_ratio_20d < 1.6),
                  f"ratio {s.vol_ratio_20d}; note {s.note}"))
    b = _bars(last_ret=-0.06)
    s = signal_at("X", b, set())
    cases.append(("-6% day: return and z-score computed", s.ret_1d is not None and abs(s.ret_1d + 0.06) < 1e-9 and s.ret_z is not None and s.ret_z < -3, f"ret {s.ret_1d} z {s.ret_z}"))
    for name, ok, d in cases:
        rec.check("C", "C5 EOD anomaly detection (synthetic series)", name, ok, d, severity="critical")
    # The fixture feed: planted last-session moves
    planted = {"SARANG": (-0.042, 2.6), "MERIDIAN": (0.068, 3.4), "LOTUS": (-0.056, 1.9), "QUANTA": (0.039, 1.7), "KESTREL": (0.004, 1.1)}
    mk = {m["symbol"]: m for m in feed["market"]}
    for sym, (ret, vr) in planted.items():
        m = mk.get(sym)
        ok = m is not None and abs(m["signal"]["ret_1d"] - ret) < 0.002 and abs(m["signal"]["vol_ratio_20d"] - vr) < 0.15
        rec.check("C", "C5 EOD anomaly detection (fixture feed)", f"{sym} planted {ret:+.1%}, {vr}x", ok, f"got {m and m['signal']['ret_1d']}, {m and m['signal']['vol_ratio_20d']}")
    an = mk.get("ANVIL")
    rec.check("C", "C5 EOD anomaly detection (fixture feed)", "ANVIL split: price move on the split day not treated as a crash", an is not None and (abs(an["signal"]["ret_1d"] or 0) < 0.2), f"{an and an['signal']}" [:200])
    rec.check("C", "C5 EOD anomaly detection (fixture feed)", "HELIX without price data: stated unavailable", "HELIX" not in mk and any(u.get("symbol") == "HELIX" or "HELIX" in json.dumps(u) for u in feed["unavailable"]),
              str([u for u in feed["unavailable"] if "HELIX" in json.dumps(u)])[:200])
