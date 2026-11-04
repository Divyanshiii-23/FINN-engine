# Testing

Everything below was run on **4 November 2026**, from a fresh clone of the release commit, in production mode (`deploy/start.sh`). Raw results are in `eval/results/*_final.json`.

## Results at release

| Suite | What it checks | Result |
|---|---|---|
| Engine unit tests (`engine/tests`, `pytest`) | Parsers, claims, ledger, credibility, Ask FINN and its validator, dedupe, materiality, market signals, service security (SSRF, auth, body limits, job caps), bank and edge-case statements, eval regressions, no fixture symbol colliding with a real NSE ticker | **251 passed** |
| Engine evaluation (`eval/run_engine_eval.py`) | A data integrity · B research quality · C push intelligence · E AI reliability, against independent re-checks and hand-labelled gold sets | **573 / 581 checks**; the 8 misses are listed below |
| Alert thresholds (`eval/alerts_eval.ts`) | The web app's own `computeAlerts` (`lib/push.ts`): defaults, threshold moves, boundaries, mute, category rules, floors, the 7-day window | **22 / 22** |
| Product in the browser (`eval/ui_eval.py`) | Ticker search, navigation and deep links, every internal link, filters, loading states, error states (500, 502, bad JSON, engine down), 6 viewports × 8 routes without overflow, WCAG 2.5.8 targets | **139 / 139** |
| Journey suites (`qa/`) | Research page, Ask FINN (phone and desktop), push screens, credibility tracker, review fixes | all pass (15/15, 18/18, pass, pass, 22/22) |
| Static demo (local server) | The exact files published: routing, search, reports, evidence and source viewer, credibility, alert rules, `&` tickers, no overflow, engine-only features disabled with a reason | **18 / 18** before publishing |
| Clean install | Clone → `pip install -e engine` → `npm ci` → `next build` → `deploy/start.sh` (data built on first start) → `/api/health` ok, engine reachable | pass |
| Read-only web (no engine) | Feed, reports, search and health served; research POST and Ask return `503 ENGINE_NOT_CONFIGURED` with instructions | pass |

## Known failures at release (engine evaluation)

- **Retrieval, 2 of 44 checks:**
  - "cement price realisation" ranks the relevant passage 4th (BM25).
  - "borrowing costs" in an Ask theme answer shows no on-topic passage.
- **Guidance extraction, 4 of 56 sentences:** guidance that states no period ("lower end of our range", "revised … to 6–8%") is kept as commentary, by design (DECISIONS.md §3). Two of these are marked critical in the gold set.
- **Materiality, 2 of 110 announcements:** a rating outlook cut to Negative scores routine, and a ₹200 cr CP allotment scores brief where the label says routine.

## What has not been tested

- **Real filings and live endpoints.** The sandbox can't reach NSE, BSE or Yahoo. On-demand research for a real ticker was run and ends in `SOURCES_UNAVAILABLE` (company, ISIN and failed fetches listed) after about 27 s.
- **The Docker image build.** Docker Hub is blocked here. The Dockerfile's steps were run outside Docker on a clean clone (above).
- **The hosted demo in a real browser.** It is a private claude.ai page, and this sandbox can't load its content frame. The owner should open it signed in and run DEMO.md steps 1–5.
- **A real language model.** The optional model path is tested only with fake completers, including an adversarial one.

## How the evaluation was built, and its caveats

See EVAL.md. In short:
- Reported figures are re-read from each PDF page by an extractor written for the evaluation, not by FINN's parser.
- Computed facts are recomputed from their inputs.
- Classification, materiality and guidance are scored against labelled sets, including a second set written after the first round of fixes.

The fixtures were written by FINN's author, so area A shows consistency, not robustness to real layouts. The first-round fixes were made while looking at set 1, so set 2's pre-fix score (83% category, 77% tier) is the fair estimate.

## Running the tests

```bash
cd engine && python -m pytest -q                                    # unit tests, about 70 s
python eval/run_engine_eval.py <label>                              # engine evaluation, about 45 s
(cd eval && npm ci && npx tsx alerts_eval.ts <work-dir>/feed.json <label>)   # work dir printed by the line above
./deploy/start.sh &                                                 # then, with the app on :3000:
python eval/ui_eval.py <label>                                      # browser suite, about 6 min
for s in qa/*.py; do python "$s"; done                              # journey suites
python eval/summarize.py engine_baseline engine_final               # before/after table
```

The browser suites need `pip install playwright && playwright install chromium`. `FINN_URL` points them at another address.
