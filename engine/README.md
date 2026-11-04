# FINN engine: push intelligence

Turns exchange filings and end-of-day prices into a ranked, explained feed.

```
filing ─► normalise ─► de-duplicate ─► classify ─► cluster into events
       ─► fetch attachment ─► extract (results figures, facts)
       ─► market reaction (EOD) ─► materiality ─► explanation ─► store ─► feed.json
```

The web app (`apps/web`) reads `apps/web/data/feed.json` through `/api/v1/feed`. It never scrapes.

Pull research (on-demand, any NSE ticker, primary sources only) is documented in [`RESEARCH.md`](RESEARCH.md).

The code review is in [`../REVIEW.md`](../REVIEW.md) and the evaluation suite and its results in [`../EVAL.md`](../EVAL.md) (`eval/`).

## Run it

```bash
pip install -e ".[dev]"          # requests, pydantic, pyyaml, pymupdf, pytest

# Synthetic fixtures: builds test inputs and writes a feed labelled dataset="fixture"
python -m finn_engine fixtures

# Live: BSE announcements (+ NSE with --nse) and Yahoo Finance EOD for portfolio.yaml
python -m finn_engine run --from 2026-10-28 --to 2026-11-04 [--nse]

# Real files you exported yourself (BSE API JSON, NSE JSON, yfinance CSV / Yahoo chart JSON)
python -m finn_engine run --inputs path/to/dir --dataset live
#   dir/bse/<SYMBOL>.json  dir/nse/<SYMBOL>.json  dir/eod/<SYMBOL>.csv  dir/attachments/<file>.pdf

# Read a feed from the terminal
python -m finn_engine digest --hours 24
python -m finn_engine alerts --price 5 --volume 2 --categories results,credit_rating

python -m pytest -q              # 251 tests (push and research)
```

Optional model phrasing of explanations: set `GEMINI_API_KEY` and `FINN_EXPLAIN_MODEL`. The template explainer is the default; model output is kept only if it adds no number, cause, judgement or name to the inputs (`explain.grounded`). No real model has been run; the path is tested with fake completers.

## Integrity rules

- **No invented filings.** Every event is built from source rows. Every announcement stores its exchange, source id, filing time (IST), fetch time, the raw payload's location, and links when the source provides them.
- **Synthetic data is labelled everywhere.** Fixture rows carry `_FINN_SYNTHETIC_FIXTURE: true` and use fictional companies whose codes (9901xx) are not real BSE codes. Fixtures never link to an exchange URL. The feed declares `dataset: "fixture"`, and the UI shows it on every screen.
- **Gaps are reported, not filled.** A failed fetch, a missing attachment or a missing price history appears in `sources`, `unavailable` and on the affected event.
- **Code does the arithmetic.** Revenue, EBITDA, PBT and PAT are extracted from the results PDF by position. EBITDA, margins, QoQ, YoY, returns, volume ratios and z-scores are computed in Python, with formulas and source rows recorded.
- **The reasoning is inspectable.** Every score is a sum of named components, each with points, a sentence and its inputs.

## What each stage does

| Stage | Module | Method |
| --- | --- | --- |
| Sources | `sources/bse.py`, `nse.py`, `yahoo.py`, `files.py` | BSE `AnnSubCategoryGetData` (paginated), NSE corporate announcements (cookie warm-up), Yahoo chart API; importers for the same formats. Polite client: spacing, retries, raw payloads kept |
| Normalise | `sources/bse.py` | IST timestamps from `DissemDT`/`DT_TM`; attachment URL from `ATTACHMENTNAME`; a **company-name guard** rejects rows whose filer doesn't match the configured company, so a wrong scrip code can't attach another company's filings |
| De-duplicate | `dedupe.py` | Exact re-post (same attachment or text), cross-exchange copy (≤45 min apart with similar text or the same file size, or ≤6 h when near-identical), and revisions (corrigendum or revised: kept and linked to the original, never dropped) |
| Classify | `classify.py`, `taxonomy.py` | All 17 categories of the ENAM reference, plus subtypes, via ordered rules. Routine compliance is matched first. Unknown filings are shown as "needs review", never buried |
| Cluster | `dedupe.py` | Same company and category within 36 h form one event (results + presentation + press release); routine filings stand alone |
| Results | `extract/results.py` | Rows rebuilt from word positions; columns located by header dates (SEBI order: this quarter, previous quarter, year-ago quarter); units converted (lakh, crore, million); consolidated preferred; checks for required rows and PBT − tax = PAT; lenders get no EBITDA |
| Facts | `extract/facts.py` | Amounts (₹ crore), rating moves, person/role/action, pledge %, dividend per share, record date: literal pattern matches only |
| Market | `market.py` | Adjusted-close returns; volume vs the previous 20 sessions (today excluded); z-score vs 60-day volatility; split days flagged; the reaction session is the first close after the filing |
| Materiality | `materiality.py` | Type prior + size relative to market cap or revenue + results surprise (PAT YoY, margin) + seniority + pledge level + market reaction. Routine items capped at 30; hard floors at 70 for downgrades, auditor resignations, pledge invocations and insolvency. Tiers: interrupt ≥ 65, brief ≥ 35 |
| Explanation | `explain.py` | "What happened" from facts and figures; "why it matters" from the top components. Optional LLM rephrasing behind a numeric-grounding check |
| Feed | `export.py` | Dataset label, source health, gaps, rejected rows, companies with EOD bars, latest-session signals with explaining-filing windows, scored events |

## Limitations

**Not yet run against live sources.** This build was developed in an environment that cannot reach BSE, NSE, Yahoo or screener.in, so it was tested only on synthetic fixtures.
- The BSE parser follows the response fields in the recorded sample published with the open-source BseIndiaApi project.
- The NSE field mapping and the Yahoo chart parsing follow their commonly documented formats and are **unverified** against live responses.
- The first live run should be checked by hand.

**Configuration**
- The BSE codes in `portfolio.yaml` must be verified. The name guard rejects mismatched rows, but a wrong code means that company's filings are missing.
- `market_cap_cr` and `revenue_ttm_cr` are blank for the live portfolio, so the size component reports "not assessed" until they are filled.

**Classification.** It uses regular-expression rules, and accuracy on a real feed hasn't been measured. Filings that no rule matches are surfaced for review rather than classified by a model.

**Results extraction**
- Works on text-layer PDFs only. There's no OCR, so scanned filings are reported as such.
- Tested on a synthetic SEBI-format statement. Real filings vary: tables spanning pages, merged cells, missing header dates (then column order is assumed and the result is flagged for review), and lender formats.
- XBRL isn't used yet.
- EBITDA is defined as PBT before exceptional items + finance costs + D&A − other income.

**Scoring**
- Weights are hand-set priors, not calibrated.
- There's no surprise-against-guidance term yet; that needs the Promise Ledger. A results filing that misses guidance can therefore rank only "worth a look" when its YoY change is small.
- Fact extraction is pattern-based and misses things phrased unusually.

**Market data**
- End-of-day only. Price and volume alerts are checked once after the close, not intraday.
- Bonus issues are caught only if Yahoo reports them as split events.
- The volume baseline needs 15 prior sessions and the volatility baseline needs 30 prior returns; below that, the values are reported as unavailable.

**Duplicate handling.** The time-window and similarity thresholds haven't been tuned on real data, and very differently worded NSE and BSE copies can slip through. Clustering can merge two unrelated filings of the same category within 36 hours.

**Delivery**
- No push notifications: alerts appear in the in-app inbox.
- No scheduler is configured. Run the pipeline from cron or GitHub Actions (hourly for filings, after the 15:30 IST close for prices).
- The store is SQLite only (portable SQL, but no other database is implemented); the feed is a JSON file.
- Alert rules are per device (`localStorage`).

**LLM explanations** are off by default and haven't been exercised live. The grounding check is numeric only.
