# FINN evaluation suite

See `../EVAL.md` for the report and how to re-run.

* `run_engine_eval.py`: areas A, B, C, E on a fresh fixture build (`eval_data.py`, `eval_research.py`, `eval_push.py`)
* `alerts_eval.ts`: C4 alert thresholds against the web app's `lib/push.ts` (`npx tsx`, installed here only)
* `ui_eval.py`: D in Chromium against the running app
* `gold/`: hand-labelled held-out sets (set 2 files were written after the fixes to set 1)
* `results/`: every run's checks, with pass/fail, severity and the evidence for each
* `summarize.py`: side-by-side table of runs
