# Testing

Everything below was run on **4 November 2026**, from a fresh clone of the release commit, in production mode (`deploy/start.sh`). Raw results are in `eval/results/*_final.json`.

## Results at release

All of this was re-run on **4 November 2026** (22:00–23:00 IST) from a **fresh clone of the release commit**:
- a new virtualenv, `npm ci` and `next build`;
- `deploy/start.sh` with `FINN_ENGINE_TOKEN` set: the production start path.

Raw results: `eval/results/*_release_verify.json`.

| Suite | What it checks | Result |
|---|---|---|
| Engine unit tests (`engine/tests`, `pytest`) | Parsers, claims, ledger, credibility, Ask FINN and its validator, dedupe, materiality, market signals, service security (SSRF, auth, body limits, job caps), bank and edge-case statements, eval regressions, no fixture symbol colliding with a real NSE ticker | **251 passed** |
| Engine evaluation (`eval/run_engine_eval.py`) | A data integrity · B research quality · C push intelligence · E AI reliability, against independent re-checks and hand-labelled gold sets | **573 / 581 checks**; the 8 misses are listed below |
| Alert thresholds (`eval/alerts_eval.ts`) | The web app's own `computeAlerts` (`lib/push.ts`): defaults, threshold moves, boundaries, mute, category rules, floors, the 7-day window | **22 / 22** |
| Product in the browser (`eval/ui_eval.py`) | Ticker search, navigation and deep links, every internal link, filters, loading states, error states (500, 502, bad JSON, engine down), 6 viewports × 8 routes without overflow, WCAG 2.5.8 targets | **139 / 139** |
| Demo walkthrough (`qa/demo_walkthrough.py`) | Every claim DEMO.md asks the presenter to make, on a 390 px phone viewport, against the running app | **29 / 29**, after DEMO.md was corrected (below) |
| Journey suites (`qa/`) | Research page 15/15; push screens pass; credibility pass; review fixes 22/22; Ask FINN (phone and desktop) | Ask FINN **17/18 on the first run, then 18/18 on five further runs.** The one failure, right after cold start, was not reproduced and is recorded as flaky. |
| Static demo files (`qa/static_demo.py`) | The exact published files (hashes match the hosted artifact's file list), served locally: 8 routes × 3 widths render without overflow, search including `&` tickers, report → evidence → source page, engine-only features disabled with a reason, brief → event | **58 / 58** |
| Clean install and production start | Clone → venv → `pip install -e engine[dev]` → `npm ci` → `next build` → `deploy/start.sh` | Up in about 20 s. `/api/health` ok: feed 29 events, 5 reports, engine reachable. SQLite created from nothing (37 announcements, 29 events, 2,080 bars). Engine answers 401 without the token, and is bound to 127.0.0.1 (refused on the host's network address, while the web app answers there). |

**Corrected during release verification.** DEMO.md described the brief before the evaluation fixes changed the ranking: it said the order win and the acquisition were under *Needs you*. It also gave other details the screens don't show:
- a floor component on SARANG;
- a −4.2% price alert, where the alert is actually on volume;
- "what was searched" for CORAL.

The walkthrough script found each one, and DEMO.md now matches the app.

## Known failures at release (engine evaluation)

- **Retrieval, 2 of 44 checks:**
  - "cement price realisation" ranks the relevant passage 4th (BM25).
  - "borrowing costs" in an Ask theme answer shows no on-topic passage.
- **Guidance extraction, 4 of 56 sentences:** guidance that states no period ("lower end of our range", "revised … to 6–8%") is kept as commentary, by design (DECISIONS.md §3). Two of these are marked critical in the gold set.
- **Materiality, 2 of 110 announcements:** a rating outlook cut to Negative scores routine, and a ₹200 cr CP allotment scores brief where the label says routine.

## What has not been tested

- **Real filings and live endpoints.** The sandbox can't reach NSE, BSE or Yahoo. On-demand research for a real ticker was run and ends in `SOURCES_UNAVAILABLE` (company, ISIN and failed fetches listed) after about 27 s.
- **The Docker image build.** Docker Hub is blocked here. The Dockerfile's steps were run outside Docker on a clean clone (above).
- **The hosted demo URL.** It is a private claude.ai page. This session can't fetch it (the URL isn't on the network allowlist), and the in-session artifact viewer isn't available here either. What was tested is the identical file set over a local server (58/58 above). The owner should open the URL signed in and run DEMO.md steps 1–5 there before sharing it.
- **The full application at a public URL.** It hasn't been deployed: there are no hosting credentials in the build environment (see LIMITATIONS.md).
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
python eval/summarize.py engine_baseline engine_release_verify      # before/after table
python qa/demo_walkthrough.py                                       # DEMO.md, claim by claim
python3 -m http.server -d static-demo/dist 4000 & FINN_STATIC_URL=http://127.0.0.1:4000 python qa/static_demo.py
```

The browser suites need `pip install playwright && playwright install chromium`. `FINN_URL` points them at another address.
