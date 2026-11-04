# Journey suites (Playwright)

Run against a running app (`FINN_URL`, default http://localhost:3000; screenshots to `FINN_QA_OUT`, default /tmp/finn-qa):

| Script | Covers |
|---|---|
| `research_interact.py` | Research home, report sections, evidence sheet, refresh, invalid ticker, company without documents |
| `ask_ui.py` | Ask FINN on phone and desktop: answers, citations, sources, out of scope, history |
| `push_interact.py` | Brief, alerts, rules, events, moves, unavailable attachment, no-feed state |
| `cred_shots.py` | Credibility tracker on four companies, overflow checks |
| `review_ui.py` | Review fixes: sticky nav, Ask history versioning, textarea, sheet focus trap, link schemes |

`pip install playwright && playwright install chromium`. The broader product suite is `eval/ui_eval.py`.
