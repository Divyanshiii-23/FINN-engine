# Architecture

## Components

```
                 ┌────────────────────────────── engine/ (Python 3.11+) ───────────────────────────────┐
 BSE / NSE APIs  │  PUSH (batch)                                   PULL (on demand)                     │
 Yahoo EOD   ───►│  sources → normalise → dedupe → classify →      resolve ticker → discover documents → │
 (or saved       │  cluster → extract (results PDF, facts) →       download (exchange hosts only) →      │
  payloads /     │  market reaction → materiality → explanation    parse statements, transcripts, decks → │
  fixtures)      │      │                                          facts registry → claims → ledger →     │
                 │      ▼                                          credibility → sections → audit         │
                 │  SQLite store ──► feed.json                         │              ▲                   │
                 │                                                     ▼              │                   │
                 │                                   <SYM>.json + <SYM>.passages.json  Ask FINN (BM25 +    │
                 │                                   (reports)                       rules, validator)  │
                 │                         research HTTP service (127.0.0.1:8787, optional token) ◄─┘    │
                 └──────────────────────────────────────────────┬──────────────────────────────────────┘
                                                                │ /v1/research, /v1/ask, /v1/securities …
                 ┌──────────────── apps/web/ (Next.js 15, React 19, Tailwind 4) ───────────────────────┐
 Browser ◄──────►│  /api/v1/feed       reads feed.json                                                 │
 (phone first)   │  /api/v1/research…  proxies the engine (token added server-side) or reads reports   │
                 │  /api/v1/ask/…      proxies the engine; 503 with a reason if there is none           │
                 │  /api/health        feed / reports / engine reachability                             │
                 │  Screens: Brief · Portfolio · Alerts (+rules) · Event · Market move · Research ·    │
                 │           Company report (8 sections + Ask FINN) · Credibility tracker · Sources    │
                 └─────────────────────────────────────────────────────────────────────────────────────┘
 static-demo/: the same screens bundled with a hash router and a data layer that answers /api/v1/* from the
               built JSON (no engine): what the hosted demo runs.
```

The engine is the only component that touches the outside world or does arithmetic. The web app never scrapes and never computes a financial figure. It reads JSON the engine wrote and applies the user's own alert thresholds and category rules at read time (`apps/web/lib/push.ts`).

## Push pipeline (`engine/finn_engine/`)

| Stage | Module | What it does |
|---|---|---|
| Sources | `sources/bse.py`, `nse.py`, `yahoo.py`, `files.py` | BSE announcements (paginated, truncation reported), NSE announcements, Yahoo chart API; importers for saved payloads. Retries, per-host spacing, raw payloads kept. Downloads limited to exchange hosts. |
| Normalise | `sources/bse.py` | IST times; attachment URLs; a filer-name guard rejects rows from another company. |
| Deduplicate | `dedupe.py` | Re-posts, cross-exchange copies (≤45 min, or ≤6 h when near-identical), revisions kept and linked, never dropped. |
| Classify | `classify.py`, `taxonomy.py` | Ordered rules over subject, headline and exchange sub-category. Covers the ENAM reference's 17 categories plus subtypes; unmatched filings shown as "needs review". |
| Cluster | `dedupe.py` | Same company and category within 36 h form one event. |
| Extract | `extract/results.py`, `extract/facts.py` | Results figures by word position and header dates; amounts, rating moves, roles, pledge %, dividend. |
| Market | `market.py` | Adjusted returns; volume against the previous 20 traded sessions (suspensions excluded, reset at splits); z-score against 60-day volatility. |
| Materiality | `materiality.py` | A score as a sum of named components (type, size relative to the company, results surprise, seniority, pledge level, market reaction), routine caps, hard floors. Tier: interrupt ≥ 65, brief ≥ 35. |
| Explain | `explain.py` | Template sentences from the facts; optional model rewording, kept only if it passes the grounding check. |
| Store / export | `store.py`, `export.py` | SQLite (idempotent upserts) → `feed.json`. |

## Pull research (`engine/finn_engine/research/`, detail in [engine/RESEARCH.md](engine/RESEARCH.md))

1. **Resolve.** Validates the symbol against the NSE equity list (a 2023 seed copy when NSE is unreachable), then maps ISIN → BSE code and industry. Lender detection uses the industry field, falling back to the company name.
2. **Discover and download.** Last ten quarters of results and calls, three annual reports, presentations. A BSE copy that's missing falls back to the NSE copy.
3. **Parse.** Statements are read by column header dates, with standalone and consolidated kept apart. Units are converted from lakh, crore and million. Bank (Third Schedule) and Ind AS formats are both read. Transcripts are split into speaker turns; decks into slides.
4. **Facts registry.** Every number is a fact. A reported fact carries document, page, row and column; a computed fact carries its formula and inputs. Text can only cite facts.
5. **Claims.** Management sentences become guidance (explicit numeric or words only), assertions or outlook. Rules decide; vague phrases are never turned into numbers.
6. **Ledger and Narrative vs Numbers.** Guidance is followed across calls (repeated, revised, dropped, withdrawn) and checked against reported outcomes. The findings are commentary against numbers, documents that disagree, and narrative shifts.
7. **Credibility tracker.** Delivery rates, revisions, capex execution and cash against profit, each with its observations. No score is given with fewer than four closed observations over two years.
8. **Sections and audit.** Eight report sections. The audit checks every quote is on its page and every computed fact has inputs.

**Ask FINN** (`research/ask.py`):
- Detects the intent (explain a change, call-to-call difference, promises, cash against profit, trend, lookup, out of scope).
- Retrieves with BM25 over passages, plus a small domain synonym map.
- Builds answer blocks only from facts and passages, then validates each one: citations must resolve and numbers must appear in the cited evidence. In model mode, added causes and low word overlap are also rejected.
- Returns `answered`, `partial`, `insufficient` or `out_of_scope`.

## Data sources

| Source | Endpoint | Used for | Verified live? |
|---|---|---|---|
| BSE announcements | `api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w`; attachments under `www.bseindia.com/xml-data/corpfiling/` | Push filings; research documents | Field mapping matches a recorded sample; not fetched from this sandbox |
| BSE scrip list | `api.bseindia.com/BseIndiaAPI/api/ListofScripData/w` | ISIN → BSE code, industry, market cap | No |
| NSE announcements | `www.nseindia.com/api/corporate-announcements` (cookie warm-up) | Push (optional), research documents and fallbacks | No (NSE often blocks cloud IPs) |
| NSE annual reports | `www.nseindia.com/api/annual-reports` | Annual report PDFs | No |
| NSE equity list | `nsearchives.nseindia.com/content/equities/EQUITY_L.csv`; seed copy dated 5 Nov 2023 in `research/seed/` | Ticker validation and search | Seed copy only |
| Yahoo Finance chart API | `query1.finance.yahoo.com/v8/finance/chart/{symbol}` | EOD prices, volumes, split events | No |
| Company IR documents | Supplied by the operator as `ir/<SYMBOL>.json` in an `--inputs` directory | Extra primary documents | Code path tested with local files |

**Not used:** news, broker reports, aggregators, or model knowledge. Under SEBI LODR, results, transcripts and presentations are filed with the exchanges, so those are FINN's primary sources.

**Demo data.** `finn fixtures` and `finn research-fixtures` generate fictional companies:
- symbols that are not real NSE tickers (a test enforces this);
- ISINs `INFIXT…` and BSE codes `9901xx`;
- PDFs in SEBI layouts, each stamped "SYNTHETIC TEST DOCUMENT";
- planted scenarios with known correct verdicts.

The feed and reports declare `dataset: "fixture"`, and the UI shows it on every screen.

## AI model choices

| Where | What runs | Why |
|---|---|---|
| Classification, materiality, extraction, claims, ledger, credibility, Ask FINN | **Deterministic rules and arithmetic in Python. No model by default.** | Every output is reproducible and explainable, and no figure can be invented. The rules are tested against held-out labelled sets (EVAL.md). |
| Retrieval | BM25 (lexical) plus a hand-written synonym map | Each match can be explained by its words, and it runs anywhere with no API key. Its paraphrase recall is weaker than embeddings would give. |
| Optional wording: push explanations, credibility interpretations, Ask FINN answers | Google Gemini via `generativelanguage.googleapis.com`, enabled only when `GEMINI_API_KEY` and `FINN_EXPLAIN_MODEL` are both set; the model name is the operator's choice | The model may reword, never decide. Its output is kept only if every number is in the inputs, it adds no cause, judgement or name, and most content words trace to the evidence (`explain.grounded`, `ask.validate`). Otherwise FINN's own sentence is shown. |
| Building FINN | Claude Code (Anthropic) | See the AI build history in README.md. |

**Status of the model path:** it has been exercised only with fake completers in tests, including an adversarial one that invents numbers and causes. No API key was available while building, so **no real model has been run**, and none is needed for any feature.

## Deployment

One container (`Dockerfile`):
- Node 22 slim with Python in a virtualenv.
- The Next build is copied in, and the demo data is generated at build time.
- `deploy/start.sh` starts the engine on 127.0.0.1:8787 and then the web app on `$PORT`, exiting if either dies.
- The health check calls `GET /api/health`.
- It runs as a non-root user.

The engine is never exposed publicly: the web app proxies it and adds the token. The static demo (`static-demo/`) is a separate build of the same React components for hosts that can't run a server. Its router maps paths to hash names (`#research-HALCYON`), and its data layer answers the API from the bundled JSON with the same responses the real routes give without an engine.
