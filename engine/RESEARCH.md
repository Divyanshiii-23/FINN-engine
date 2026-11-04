# FINN engine: Pull research

On-demand research for any NSE ticker, built only from the company's own
disclosures. No model is called: every figure, comparison and finding is
produced by code and cites the document, page and row or quote it came from.

```
ticker ─► resolve (NSE equity list → ISIN → BSE scrip code)
       ─► discover (BSE + NSE announcements, NSE annual reports, optional IR documents)
       ─► select (latest 10 results quarters; their transcripts and presentations; latest 3 annual reports)
       ─► download (falls back to the other exchange's copy)
       ├─► numbers path:   results PDFs → P&L, balance sheet, cash flow, segments → computed metrics
       └─► narrative path: transcripts / decks / annual report → speaker turns → sentences → typed claims → gates
       ─► join (promise ledger, assertion checks, tone shifts, discrepancy rules)
       ─► credibility (indicators, timeline lanes, interpretation)
       ─► eight sections ─► evidence audit ─► report JSON
```

## Run it

```bash
python -m finn_engine research RELIANCE            # live: NSE, BSE (needs network access to both)
python -m finn_engine research KAVERI --inputs DIR # saved exchange payloads (see FileInputs in research/sources.py)
python -m finn_engine research-fixtures             # build the synthetic test companies and their reports
python -m finn_engine serve --port 8787             # on-demand API for the web app (set FINN_ENGINE_URL there)
python -m finn_engine ask KAVERI "Why did margins decline?"   # Ask FINN from the command line
python -m pytest tests -q                           # 226 tests (see REVIEW.md for the review regressions)
```

Reports go to `apps/web/data/research/<SYMBOL>.json` with an `index.json`;
`research-fixtures` also writes `securities.json`, the ticker list the web
app searches when no engine is connected.

`serve` answers `GET /v1/securities?q=`, `GET /v1/research`, `GET|POST
/v1/research/<SYMBOL>` and `GET /v1/research/<SYMBOL>/job`. A POST starts a
background job; the job reports its stage and ends `done` or `error` with a
code (`INVALID_SYMBOL`, `UNKNOWN_SYMBOL`, `UNVERIFIED_SYMBOL`,
`SOURCES_UNAVAILABLE`, `INTERNAL`). Fixture companies are served from the fixture
directory; every other ticker goes to live sources.

Hardening: the service binds to 127.0.0.1 by default. Set `FINN_ENGINE_TOKEN`
on both the engine and the web app to require `Authorization: Bearer <token>`
on every route except `/health` (the web app adds it server-side). At most two
research runs execute at once (`429 BUSY` beyond that); request bodies are capped
at 4 KB; tracebacks go to the server log, never to the client. Attachment URLs
taken from exchange payloads are fetched only over https from `bseindia.com` /
`nseindia.com` hosts (redirects included), and local paths are read only for
documents the operator supplies.

## Sources, and what isn't used

| Source | Used for |
| --- | --- |
| NSE equity list (`EQUITY_L.csv`) | validating the ticker, name, ISIN, series |
| BSE scrip list (`ListofScripData`) | ISIN → BSE code, industry, market cap (exchange data, labelled as such) |
| BSE corporate announcements | results filings, call transcripts, investor presentations, press releases, annual report |
| NSE corporate announcements | the same documents as filed on NSE; also a fallback copy when a BSE attachment is missing |
| NSE annual-reports API | annual report PDF |
| `ir/<SYMBOL>.json` in an `--inputs` directory | documents you add from the company's IR site (there is no command-line flag for single documents) |

Not used: news, broker reports, aggregator sites, and model knowledge. Under
SEBI LODR, transcripts and presentations must be filed with the exchanges, so
the exchange copies cover the investor-relations disclosures without
scraping company websites. A filing whose filer name doesn't match the
company is rejected and listed.

When NSE can't be reached, tickers are checked against
`research/seed/nse_equity_list_2023-11-05.csv`, a dated copy of NSE's list
(provenance in `research/seed/SOURCE.md`). The report says so, and a ticker
missing from that copy is `UNVERIFIED_SYMBOL`, not "unknown".

## Four kinds of information, kept apart

| Class | What | Where it comes from |
| --- | --- | --- |
| `reported` | A figure as printed in a results statement | page, row text, column date, basis (consolidated preferred) |
| `guidance` | A forward-looking statement about a metric and a period | quote, speaker, section (prepared remarks / Q&A), page |
| `assertion` | Management describing a reported period ("revenue grew 7.4%") | quote, as above; checked against reported figures |
| `outlook` | Qualitative commentary with no metric target | quote, theme, word-list tone |
| `computed` | Everything FINN derives: growth, margins, EBITDA, net debt, credit cost, gaps, run-rates | formula and the facts it used |

**Explicit guidance** states a number: a range, a point, a floor, a ceiling,
a bps change, or "double-digit" / "doubling" read literally (≥ 10%, 2×).
**Qualitative guidance** gives only a direction ("margins to improve",
checked for sign) or a worded quantity ("high single digits", "healthy
growth"). Worded quantities are **never** turned into numbers: they are shown
in management's words with the actual beside them for context, and not
scored. "Around X" is read as X ± 1 pp (percentages) or ± 5% (amounts), and
that reading is shown with the verdict.

A claim survives four gates: the quote is found on the cited page; the
speaker is management (analysts and the moderator never make claims); every
number in the target appears in the quote; a guidance period is actually
stated (otherwise it becomes commentary). Further rules keep common
misreadings out: constant-currency guidance is never checked against rupee
revenue; "18% of the loan book" is a share, not growth; a direction must
attach to the metric ("margins absorbed the wage increase" is not "margins
increased"); two bases in one sentence ("1.8% sequentially and 8.2% year on
year") become two checks; foreign-currency amounts are not read as rupees.

## Narrative vs Numbers

* **Threads.** Guidance is grouped by metric, segment and period across the
  calls read. Each later statement is *reiterated*, *raised*, *lowered*,
  *changed*, *restated in words only*, *withdrawn* or *also stated* (same
  quarter, another document). A complete later transcript that doesn't
  mention an open target marks it *not repeated*. A missing transcript never
  does.
* **Verdicts.** Closed periods: *delivered* / *ahead* / *missed*, with the gap
  to the nearest edge as a computed fact. Open periods: *pending*, with the
  year-to-date actual, *on track* or *at risk*, and what the rest of the
  period needs (compared with the best quarter in the data). *Dropped* when
  withdrawn or not repeated (flagged *behind* if the numbers were already
  short). *Not checkable* when the metric isn't in the filed statements
  (constant currency, AUM, volumes, orders, utilisation, NIM on a different
  denominator), with the reason.
* **Assertions** are checked on every plausible basis (YoY, QoQ, level) and
  called *contradicted* only if none fits.
* **Narrative changes**: management's tone per theme (demand, pricing,
  margins, asset quality, regulation and others), call by call; a turn from
  positive to negative, or a new concern, is a shift.
* **Discrepancies**, each with an implication: missed guidance, guidance
  dropped or at risk, guidance lowered, contradicted assertions, and upbeat
  commentary about the quarter just reported next to falling revenue or
  margins.

## Ask FINN

Questions about one company, answered only from the documents read for its
report. It sits in the research terminal (the "Ask FINN" box on each company
page); `finn ask SYMBOL "question"` does the same from the command line, and
`finn serve` answers `POST /v1/ask/SYMBOL`.

```
question ─► scope check (no recommendations, prices, predictions or general knowledge)
         ─► intent, topics, period
         ─► retrieve passages: BM25 over transcript turns (with speaker, section, page and the
            analyst question a Q&A answer replies to), slides, annual-report pages and
            statement tables; filtered by role, document, period and tense
         ─► retrieve facts: reported figures, FINN computations, ledger entries, findings
         ─► compose blocks ─► validate every block ─► answer with a status
```

**Intents** and what each uses: *why* a metric moved (the change year on year
and quarter on quarter, each cost line's change as a share of revenue, the
revenue effect, and management's explanation from that quarter's call);
*what changed between calls* (every guidance change across all documents
filed for each quarter, tone shifts per theme, the reported figures); *cash
against profit* (OCF ÷ PAT and ÷ EBITDA by year, the latest half, flags, what
management said about cash); *promises* (ledger targets with first and final
figures, outcomes, and other forward-looking passages); *contradictions*;
*what management said about* a theme (call by call, with tone and shifts);
*trends*; anything else falls back to passage retrieval with an explicit "no
computed analysis" note.

**Blocks** keep the kinds apart: `fact` (reported or computed), `guidance`,
`management` (quoted passages), `finding`, `interpretation` (FINN's reading,
marked as such), `note` (for example a corrected premise: "the question
assumes revenue fell, but it grew 5.3%") and `gap` (evidence the question
needs that the documents don't have). Status: *answered*, *partial*
(something the question needs is missing), *insufficient* (nothing in the
documents addresses it; the answer lists what was searched) or
*out_of_scope*.

**No unsupported claims.** Every block except notes and gaps must cite
evidence that resolves; every number in a block must appear in what it cites.
Differences FINN states ("−3.0 pp", "+3.0 pp of revenue") are computed facts
with formulas, built during the research run, so a sentence never contains
arithmetic done while writing it. Blocks that fail are dropped, never shown.

**Optional model.** With `finn serve --llm` (and `GEMINI_API_KEY`,
`FINN_EXPLAIN_MODEL`), a model writes the answer from an evidence pack of the
rule answer's citations only. Each block it writes must cite pack items, use
only numbers in what it cites, and share at least half its content words with
that evidence (a third for interpretation). If no factual block survives, the
rule-written answer is returned with the reason. The model is never called for
out-of-scope or insufficient questions.

**Source navigation.** Every citation opens either the figure (formula,
inputs, row as printed) or the passage in a document viewer that pages through
the whole document, with the cited passage marked and a link to the filing at
that page when it is real.

Limits: retrieval is lexical (BM25 with topic expansion), so a question in
unusual words may miss a relevant passage; the intents cover the common
research questions, and anything else gets passages rather than analysis;
"why" answers locate a change in the statements and quote management's
explanation, but FINN doesn't establish causes. Questions about other
companies are answered only from this company's documents.

## Management credibility tracker

`report["credibility"]`, shown at `/research/<SYMBOL>/credibility`, sets what
management said against what was later reported, over the full history read
(10 quarters of calls and results, up to 3 annual reports: about three fiscal
years of promises). It reuses the ledger, numbers and claims above; it reads
no document of its own.

**No trust score.** Combining delivery, revisions and cash into one number
needs weights, and any weighting is a judgement, not a measurement. Each
indicator reports what was observed, with its count, and lists every
observation with its quote and reported figure. A rate is stated only from
**4 closed explicit targets across 2 fiscal years** (`MIN_CLOSED`, `MIN_YEARS`);
below that the indicator says "not enough history (n = 3)".

| Indicator | What is counted |
| --- | --- |
| Guidance delivery | closed explicit targets kept (delivered or ahead) vs missed, by metric family |
| Where results landed | actual minus the midpoint of the stated range, in pp (growth, margins) or % (amounts); favourable or adverse depends on the metric |
| Guidance revisions | targets changed before their period closed; "against the company" means lowered for growth/margins/capex, raised for credit cost/debt; repeated cuts on one metric across years; targets met only after a cut (first-stated figure tested too) |
| Capex execution | cash-flow capex ÷ the *first-stated* plan for the year |
| Revenue growth, margin progression | every statement for the year (explicit, worded, constant currency) beside the reported figure; only explicit ones scored |
| Cash against profit | OCF ÷ PAT and OCF ÷ EBITDA by year, beside what management said about cash (not for lenders) |
| Targets that went quiet | explicit targets not repeated, withdrawn or restated in words without being met, and what happened next |
| Figures quoted on calls | management's statements about reported periods: consistent, partly, contradicted |

**Timeline.** One lane per metric on a time axis: each explicit target is a
band from the day it was stated to the end of its period, with a new step at
each revision; qualitative statements and silences sit on a strip below; the
reported path runs through; the period outcome is a square (green kept, red
missed, hollow year-to-date). Worded targets get a dashed circle: their
actual is shown, never scored.

**Interpretation** is a separate, labelled class. It is written by fixed rules
(`credibility.Credibility.interpret`), each sentence citing the facts its
numbers come from: delivery once the gate is met, a tendency to land short
or long, repeated cuts, a target met only after being cut, capex below plan
in every closed year, a target that went quiet and was then missed, the same
metric missed in two or more years, a good record next to a slipping current
year, and cash claims the statements contradict. `finn research SYMBOL --llm`
lets a model reword these sentences, and a rewording is kept only if every
number in it appears in the cited facts. Without `GEMINI_API_KEY` and
`FINN_EXPLAIN_MODEL`, nothing is sent anywhere.

**Contradiction detection** pairs a quote with a figure:

* a figure management quoted about a reported period that no basis supports (existing);
* upbeat demand, margin or cash commentary about the quarter just reported, next to falling
  revenue, a margin down 1.5 pp or more, OCF below 60% of EBITDA, or negative free cash flow;
* "we reduced debt" while net debt rose between the two balance-sheet dates;
* the presentation and the call for the same quarter giving different targets (reported as a
  contradiction, not counted as a revision).

Limits: the tracker is only as long as the history the exchanges serve, and
transcripts filed before SEBI made them mandatory may be missing. Tone is a
word list. Rules don't read causes, so a miss management explained on the
next call is still a miss here. Targets on metrics outside the statements
(volumes, AUM, constant currency) can be listed but not scored.

## The eight sections

1. **Business snapshot**: the company's own description (annual report or
   deck, quoted), identity, segment mix from the results segment note.
2. **Financial snapshot**: latest quarter's revenue, EBITDA (NII for lenders) and PAT,
   with QoQ, YoY, margins and TTM figures. Net debt and debt to equity. Market cap and P/E.
3. **Financial trajectory**: up to eight quarters (four filings × current
   and year-ago columns), full years from Q4 filings, restatements.
4. **Balance sheet**: at the H1 and FY dates in the filings. Equity, borrowings,
   cash, net debt, working-capital and receivable days. Loans for lenders.
5. **Cash quality**: OCF, capex, FCF, OCF ÷ EBITDA, OCF ÷ PAT, with flags.
   Lenders get OCF only, with the reason.
6. **Narrative vs Numbers**: as above.
7. **Management guidance**: explicit and qualitative guidance with wording
   strength (firm / expect / aspirational / conditional), and commentary by theme.
8. **Bull vs Bear**: fixed rules over the cited facts. Every number in a
   point is in the facts it cites (tested). A side with no triggered rule is
   left empty and says so.

Every report ends with an **evidence audit** that fails the run if any
reported figure lacks a page and row, any quote lacks a page, any computed
figure lacks a formula or resolvable inputs, or any finding lacks evidence.

## Testing

The sandbox this was built in can't reach NSE, BSE or company sites, so no
real filing has been read yet. The pipeline is tested on **synthetic
companies across four sectors** (IT services, cement, NBFC, pharma, plus a
listed company with no documents), generated by `research/fixtures.py`. These
are fictional, stamped "SYNTHETIC TEST DOCUMENT" on every page, with ISINs
starting `INFIXT` and no exchange URLs, and their reports are marked
`dataset: fixture`. The documents follow real layouts: SEBI Reg. 33
statements with standalone and consolidated pages; units in crore, lakhs and
million; Indian digit grouping; lender formats; multi-page transcripts with
participant rosters and Q&A; decks; one scanned deck; MD&A. Each company
plants cases with known answers, and the tests assert them:

* every reported P&L figure equals the generator's value (over 200 checks);
* 14 planted guidance verdicts, guidance histories, segment guidance,
  words-only handling and the assertion checks;
* every quote and statement row is re-found on its cited page in the PDF;
* withdrawals don't touch closed periods; tone shifts and discrepancies fire;
* coverage: older filings excluded, NSE fallback copy, scanned PDF, filer
  mismatch, missing transcript;
* a real ticker with every source unreachable resolves from the seed list and
  stops with `SOURCES_UNAVAILABLE`; unknown, unverified and invalid symbols;
* reports are deterministic; the HTTP service runs a job end to end.

## Limitations

* **Never run on a real filing.** The parsers follow real layouts, but real
  PDFs vary more than fixtures: merged header cells, statements split across
  pages, notes inside tables, "Rs. in lakhs" on another page, two-column
  transcripts. Expect `needs_review` statuses and missed rows on the first live
  runs. The fixtures were written by the same author as the parsers, so
  passing them proves consistency, not coverage.
* **Live endpoints unverified.** The BSE announcements field mapping matches a
  recorded sample; the NSE announcements, NSE annual-report and BSE scrip-list
  mappings follow their documented formats but haven't been seen live. NSE
  often blocks cloud IPs.
* **Text-layer PDFs only.** Scanned pages are reported, not read (no OCR).
* **Rule-based claim extraction.** Precision is favoured over recall: unusual
  phrasing ("we are looking at mid-teens kind of growth") can be missed, and
  the word-list tone is crude. An LLM could propose candidates as long as the
  same gates (quote on page, numbers from the quote) decide, but none is wired
  in. Nothing in a report is model-generated.
* **Only what's in the statements is checked.** Constant-currency growth, AUM,
  volumes, order books, utilisation and NIM are shown but not scored. Credit
  cost is computed on on-book loans and may differ from the company's figure.
* **Window.** Ten quarters of results and calls and three annual reports; the
  trajectory section shows the latest eight quarters. A Q1 filing carries no balance sheet or cash flow, so
  the latest balance sheet can be up to two quarters old. Calendar-year
  reporters aren't supported.
* **Thresholds are judgement.** Tolerances (±0.5 pp, ±5%), the 60% cash
  conversion and the "at risk" tests are fixed choices, shown beside each
  finding, not fitted to data.
* **Bank format tested on a constructed page only.** Banking Regulation Act
  statements (Interest earned / Interest expended / Provisions and contingencies,
  Advances, Deposits) are recognised, but only against a synthetic page in
  `tests/test_research_statements.py`. Lender detection uses BSE's industry
  field, falling back to the company name when BSE is unreachable.
* **Price data** on the research page comes from the push feed and covers only
  companies in that feed.
