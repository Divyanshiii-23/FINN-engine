# Known limitations

Most important first. Nothing here is hidden elsewhere as working.

## Not verified against the real world

1. **No real filing has been parsed.** The build sandbox couldn't reach NSE, BSE or company websites. Every document FINN has read is a synthetic fixture written by the same author as the parsers. The 738/738 figures re-read from PDFs (EVAL.md) show internal consistency, not robustness. Real PDFs have merged header cells, statements split across pages, notes inside tables and scans; expect misses and `needs_review` statuses on first live runs.
2. **Live endpoints are unverified.** The BSE announcements mapping matches a recorded sample. The NSE announcements, NSE annual reports, BSE scrip list and Yahoo field mappings follow their documented formats but haven't been seen live from here. NSE often blocks cloud IP addresses.
3. **Bank statements are tested on a constructed page only** (Banking Regulation Act format). Lender detection uses BSE's industry field, falling back to the company name.
4. **No model has been run.** The optional Gemini wording path is tested only with fake completers. FINN works without it.
5. **The Dockerfile has not been built** (Docker Hub is blocked in the sandbox). Its steps were run outside Docker on a clean clone, where the start script and the browser suites passed (one Ask FINN check failed once after cold start and passed on five re-runs; see TESTING.md).

## Deployment

6. **The hosted demo is static.** It shows the real screens and bundled data. Ask FINN and on-demand research are disabled there (the screens say so), because no engine runs.
7. **The hosted demo URL has not been tested from the build environment.** It is published as a claude.ai artifact that only its owner can see until shared. This session can't fetch it, and can't run the artifact viewer. The exact published files (the hashes match) passed 58/58 checks over a local server (`qa/static_demo.py`). Opening the URL itself is a step the owner has to do.
8. **The full application is not deployed anywhere public.** No hosting account or token was available, and the GitHub token in the build environment is invalid, so there is no repository to deploy from. The production path (`deploy/start.sh`, which is the Dockerfile's `CMD`) was verified on a clean clone; deploying the container to a host is still to do.

## Coverage

9. **Calendar-year reporters and half-yearly SME filers are unsupported.** Periods assume April–March quarters.
10. **The ticker list behind search is a 5 Nov 2023 seed copy** when NSE is unreachable. Newer listings show as "try anyway"; renamed or delisted symbols are still listed. The static demo's list is the EQ series only.
11. **The window is ten quarters of results and calls and three annual reports.** A Q1 filing has no balance sheet, so the latest balance sheet can be two quarters old.
12. **Only what the statements contain is checked.** Constant-currency growth, AUM, volumes, order books, utilisation, attrition and NIM guidance are shown but not scored. Credit cost uses on-book loans.
13. **Guidance with no stated period is not scored** (kept as commentary). This was deliberate; see DECISIONS.md §3.
14. **Retrieval is lexical** (BM25 and a small synonym map). Some paraphrases miss.
15. **Classification and materiality are hand-written rules.** On an unseen labelled set they scored 83% on category and 77% on tier, with 9 of 14 critical events interrupting, before that set was used for fixes. Some tier calls in the gold labels are themselves arguable, and there was one annotator.
16. **The push universe is a fixed portfolio file.** There are no user accounts and no per-user portfolio storage; alert settings live in the browser's local storage.
17. **The fixture "as of" date is 4 Nov 2026.** The demo's dates will look old after that, and they are labelled as fixture data.

## Security and operations

18. **The engine token is off by default.** Without `FINN_ENGINE_TOKEN`, anything that can reach the engine port can start research runs. `start.sh` binds the engine to 127.0.0.1 for that reason.
19. **There's no per-client rate limit** on the public web routes. Research runs are capped at two concurrent.
20. **There's no scheduler for the push pipeline.** A live deployment needs a cron or job runner to call `finn run`, and none is included.
21. **Two results parsers** (push `extract/results.py`, research `statements.py`) share a row reader but not field maps, so fixes must be kept in step.

See REVIEW.md (open items O-1…O-12) and EVAL.md ("Still failing").
