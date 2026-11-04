# FINN evaluation report

Run on 4 November 2026 against the running application: the Pull and push pipelines, the research HTTP service, and the Next.js app in Chromium.

The harness and gold sets are in `eval/`; see "Re-running" at the end. Raw results for every check are in `eval/results/*.json`.

## What was tested, and against what

| Area | System under test | Ground truth |
|---|---|---|
| A. Data integrity | Full Pull pipeline on 5 fixture companies (40 results filings, 39 transcripts, decks, annual reports) | (1) Every reported figure is **re-read from its PDF page by an extractor written for the evaluation**, which locates the figure by word coordinates and not with FINN's parser. (2) Values planted by the fixture generator. (3) Independent recomputation of every QoQ, YoY and margin figure. (4) PDFs built for the evaluation (loss-making, zero-revenue, out-of-order columns). |
| B. Research quality | BM25 index, Ask FINN over HTTP, claim extraction, ledger, Narrative vs Numbers | 22 paraphrased retrieval queries with topic predicates; 30 Ask questions; 56 management sentences with gold readings (two sets); 14 planted guidance verdicts; 11 planted discrepancies and 4 must-not-flag cases. |
| C. Push intelligence | Classifier, materiality, dedupe/clustering, EOD signals, the fixture feed, and the web app's own `computeAlerts` (TypeScript) | 110 announcements labelled by hand (two sets) with acceptable categories and tiers; 28 fixture-feed labels; 11 duplicate scenarios built for the evaluation; 9 synthetic price series; threshold boundary cases. |
| D. Product | Browser: search, navigation, filters, loading, errors, 6 viewports × 8 routes | Expected behaviour per control; WCAG 2.5.8 target size. Network delays and failures were injected with route interception. |
| E. AI reliability | Ask FINN (rules and an adversarial fake model), report text | False-premise, out-of-scope, injection, insufficient-evidence and conflicting-source questions; a "model" that invents numbers, causes and citations. |

**The limit that matters most.** No real company document was available. The sandbox cannot reach NSE, BSE or company sites; real BSE PDFs turn up in web search but can't be downloaded here.

"Original company documents" therefore means FINN's synthetic, labelled fixture PDFs. Those were written by the same author as the parsers, so area A measures internal consistency and arithmetic, not robustness to real layouts. The held-out announcement and sentence sets were written for this evaluation in real filing phrasing, and are the most meaningful accuracy numbers here.

## Results

Baseline is before any product fix. Most groups are pass/total counts of individual checks; the summary rows give each area's headline measure.

| Area | Group | Baseline | After fixes |
|---|---|---|---|
| **A** | Reported figures matching an independent re-read of the PDF | 738/738 | 738/738 |
| | Computed facts recomputed from their inputs | 1,049 within tolerance | same |
| | QoQ / YoY / margin vs planted truth; negative/zero cases; missing data; period mismatches | 37/37 | 37/37 |
| **B** | BM25 retrieval hit@3, paraphrased queries (MRR) | 17/22 (0.70) | 21/22 (0.90) |
| | Ask end-to-end shows on-topic evidence | 18/22 | 21/22 |
| | Citations that resolve and are found on the cited PDF page | 273/273 | 276/276 |
| | Answer blocks whose every number is in the cited evidence | 55/55 | 55/55 |
| | Claim quotes found on their cited page | 5/5 companies | 5/5 |
| | Guidance sentences, set 1 (used for fixes) | 33/40 (1 number manufactured) | 36/40 (0 manufactured) |
| | Guidance sentences, set 2 (**unseen**) | – | 15/16 before the last fix; 16/16 after |
| | Planted ledger verdicts; Narrative vs Numbers findings and non-flags | 34/34 | 34/34 |
| **C** | Classification, set 1 (used for fixes) | 71/80 (89%) | 80/80 |
| | Tier agreement, set 1 | 57/80 (71%) | 80/80 |
| | **Critical events reaching "interrupt", set 1** | **6/24** | 22/24 |
| | Classification / tier, set 2 (**unseen**, before its fixes) | – | 25/30 (83%) / 23/30 (77%) |
| | Critical → interrupt, set 2 (unseen → after its fixes) | – | 9/14 → 12/14 |
| | Duplicate scenarios (built for the evaluation, plus the fixture feed) | 13/15 | 15/15 |
| | EOD anomaly series and fixture signals | 13/15 | 16/16 |
| | Alert thresholds via the web app's own logic | 21/22 | 22/22 |
| **D** | Ticker search; navigation; filters; loading; errors | see note | 60/60 |
| | No horizontal overflow, 6 viewports × 8 routes | 51/54 | 54/54 |
| | Tap targets ≥ 24px (WCAG 2.5.8 with its spacing/inline exceptions) | 16/24 pages | 24/24 |
| **E** | False premises, refusals, injection, insufficient evidence, conflicting sources | 12/12 | 12/12 |
| | Guidance interpretation in answers (words-only kept as words, withdrawals, conflicting ranges) | 5/5 | 5/5 |
| | Report text with numbers not in its evidence | 4/5 companies | 5/5 |
| | Adversarial model: invented numbers, causes and citations dropped | 2/2 | 2/2 |
| **Total (engine)** | | 448/504, 30 critical | 573/581, 2 critical |
| **Total (browser)** | | – | 138/138 |

Engine unit tests went from 237 to 250 (13 regressions in `engine/tests/test_eval_regressions.py`). The existing Playwright suites all still pass.

**How to read set 1 against set 2.** Set 1's post-fix 100% is optimistic, because the rules were changed while looking at it. The fair estimate for filings FINN hasn't seen is **set 2 before its fixes: 83% category, 77% tier, 9/14 critical events interrupting, 13/14 at least in the brief**. Set 2 was then used to fix five critical misses, so its post-fix numbers are tuned too.

**Note on the browser baseline.** The first UI runs mixed product failures with failures in my own checker (race conditions, label text). The product defects they found are listed below. A clean before/after total isn't meaningful for D.

## Failures found and fixed

### Critical

| Found by | Defect | Root cause | Fix |
|---|---|---|---|
| C2 | A CEO, MD or CFO resignation, a chairman's death, a pledge rising to 32%, a ₹1,250 cr order (31% of revenue) and a USFDA warning letter all landed in the brief, not as alerts. Only 6/24 critical events interrupted. | Base points too low for these events; seniority added the same points for leaving as for joining. | `taxonomy.py` priors; `materiality.py` gives +25 for senior exits, stronger pledge and size bands. |
| C2 | A buyback of "1.2 crore equity shares at ₹1,500" was sized at ₹1.2 cr. | The amount regex read a share count as rupees. | `extract/facts.py`: share counts are skipped; count × price is computed. |
| C1/C2 | NCD interest default classed as a routine debt issue. Open offer filed as an insider disclosure. Delisting, IT search, SEBI restraint order, fire and ransomware unclassified. | No rules for these types. | New rules and floors (a default always surfaces). |
| C2 | "NCLT sanctions scheme of amalgamation" raised an insolvency alert (70). | The insolvency rule matched "NCLT". | It is excluded when a scheme or merger is named. |
| C3 | Two different filings with the same generic subject ("Regulation 30 – General") and different attachments: the second was hidden as a duplicate. | The identical-subject rule ignored attachments. | It now requires the documents to be indistinguishable (`dedupe.py`). |
| C3 | The NSE copy of a filing disseminated 2h10m after BSE was shown twice. | 45-minute cross-exchange window. | Up to 6 hours when the text is near-identical or the file size matches. |
| C5 | Ten suspended (zero-volume) sessions made a 2.2× day read as 4.5×. | Zeros were averaged into the baseline. | Zero-volume sessions are excluded; the baseline needs 15 traded sessions or is stated as missing. |
| C5 | 1:2 split ten sessions ago: normal volume read as 1.6×. | Pre-split volumes were mixed in. | The baseline restarts at a split, with a note. |
| B4 | "Price increases of 3% … should support margins" became a 3% EBITDA-margin target. | The number was attached to the nearest metric. | `claims.scrub`: quantities owned by price, wage, tax or payout are removed before targets are read. |
| B4 | "Capex this year will be ₹600–650 cr, of which ₹280 cr has been spent in the first half" was dated **H1** FY27. | "first half" in the subordinate clause set the period. | "of which …" clauses are removed before period resolution. |
| B4 | "Revenue grew 14% in H1, and we expect similar momentum" became 14% H1 guidance. | The mixed-tense sentence wasn't split. | Split before ", and we expect / will …". |
| D6 | The research page scrolled sideways on 320–390px phones. | Evidence chips were fixed at 22rem, and grid items had no `min-w-0`. | `report-ui.tsx`, `ReportSections.tsx`, `NarrativeVsNumbers.tsx`, `Credibility.tsx`. |

### Normal

| Found by | Defect | Fix |
|---|---|---|
| B1 | Search stemmed query terms twice: "utilisation" → "utilis" → "utili", matching nothing. "price" and "prices" didn't match. | Stem once; normalise a trailing e; small paraphrase map (logistics → freight, FDA → USFDA, borrowing → funds, salary → wage). |
| B1 | "What did management say about fuel and power costs?" answered with all margin commentary. | Theme answers also show passages naming the specific term. |
| E4 | KAVERI's credibility text said "86%" while the cited fact showed "0.86x". | The text now quotes the fact's own display (86.5%). |
| B4 | "23% plus or minus 50 bps" was read as a point. | Parsed as 22.5–23.5%. |
| C4 | A 4.996% move showed as "+5.0%" but didn't trigger a 5% alert. | Thresholds are compared at display precision (`lib/push.ts`). |
| D1 | "TCS.NS" and "NSE:INFY" found nothing in search, although research URLs accepted them. | Prefixes and suffixes are normalised in the engine, the web fallback and the client. |
| D6 | Back links, "Full ledger", "quote, p.N", portfolio tickers, alert titles and "Change" were 15–20px targets close to others. | `min-h-6` or vertical padding. |
| C1 | Special dividend, bonus/split, business updates, ₹5,000 cr MoU and promoter block sales scored routine; a website-change notice went to "needs review". | Priors and rules; MoU size is now assessed. |

## Still failing / known limitations

1. **Guidance without a stated period isn't scored** (set 1: g11 "lower end of our range", g24 "revised … to 6–8%", g27, g33). FINN keeps these as commentary rather than assume the current year. This is a recall gap of 4/17 explicit guidance sentences, kept deliberately; the alternative risks scoring a target against the wrong year.
2. **Retrieval is lexical.** One paraphrase still misses ("cement price realisation" ranks the right passage 4th); "borrowing costs" end-to-end shows the cost-of-funds passage only via synonym search, not in the theme answer. The synonym map is hand-written and small.
3. **Remaining tier disagreements on unseen set 2:** a rating outlook cut to Negative (scored routine as a reaffirmation) and a ₹200 cr CP allotment (scored brief; gold says routine). Two set-1 critical items reach the brief but not interrupt.
4. **No real-document test** (see above). The 738/738 figure re-read is on PDFs FINN's author produced. Real filings with merged cells, split statements and scans will produce misses that this suite cannot see.
5. **Gold labels are one analyst's judgement.** I wrote them, and some tier calls (an order of 31% of revenue: brief or interrupt?) are arguable. Ambiguity is encoded as acceptable sets, but there is no second annotator.
6. **Tap-target check is an approximation of WCAG 2.5.8.** Spacing is measured centre to rectangle. Inline-in-sentence figures are exempt.
7. **Live path.** An arbitrary ticker (ASIANPAINT, timed fresh) resolves to the right name and ISIN, then ends with `SOURCES_UNAVAILABLE` after 27s with its 5 failed fetches listed. In the browser POLYCAB does the same. Live parsing of real filings is untested.

## Evaluator errors I made and corrected

These were mistakes in the harness, not the product. Each was corrected before the baseline was recorded.

- The PDF re-reader grouped words by text block, so it initially "failed" 733 figures. Labels and figures sit in separate blocks, so rows are now grouped by y-position.
- It treated borrowings and payables summed across sections as mismatches. Each source row is now re-read and summed.
- Debt/equity is stored to 2 decimals; the change in net debt is not a pp value.
- Gold corrections:
  - "about 10%" → FINN's displayed 9–11% band accepted;
  - HALCYON has no planted contradiction, so "none fired" is correct;
  - a board notice a week before results is rightly a separate event;
  - a split resets the volume baseline instead of giving a ratio, both of which are honest.
- Two boundary cases were changed after the C4 fix, because the threshold now applies at display precision (4.94% rather than 4.99%).
- In the browser: a search race (the "Try X anyway" row matched first), route handlers that blocked Playwright's loop, and badge text in nav labels.

## Re-running

```bash
python eval/run_engine_eval.py <label>                       # A, B, C (not C4), E on a fresh build; ~40s
cd eval && npx tsx alerts_eval.ts <feed.json> <label>        # C4 against apps/web/lib/push.ts (feed.json is in the work dir the line above prints)
python eval/ui_eval.py <label>                               # D; needs `finn serve` on :8787 and `next start` on :3000 with FINN_ENGINE_URL
python eval/summarize.py engine_baseline engine_after_fixes   # side-by-side table
```
