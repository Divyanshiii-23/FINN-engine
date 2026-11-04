# FINN: a mobile-first investment agent for Indian equities

FINN does two jobs for someone holding NSE-listed stocks.

- **Push: what changed and why it matters.** FINN reads exchange filings and end-of-day prices for a portfolio. It removes duplicates, classifies each filing and scores how material it is (the score is a sum of named, inspectable components). It then explains each event and turns it into a brief and alerts against the user's own thresholds.
- **Pull: research any NSE ticker from primary sources.** FINN reads the company's results filings, call transcripts, presentations and annual reports. It builds an eight-section report with every figure and quote traceable to a document page, and compares management's guidance with what was delivered (Narrative vs Numbers, plus a management credibility tracker). **Ask FINN** answers questions only from those documents, with citations, and says when the evidence isn't there.

Built for the ENAM Holdings AI Engineer Build Challenge by Divyanshi Agnihotri (IIT Kanpur), with Claude Code. See [AI build history](#ai-build-history).

> **Data in this build is synthetic and labelled.** The sandbox FINN was built in could not reach NSE, BSE or company websites. The demo therefore runs on fictional companies whose documents follow real SEBI filing layouts. Every screen says so, and every document carries a "SYNTHETIC TEST DOCUMENT" stamp. The live-source code paths exist and degrade honestly when sources are unreachable, but they have **not** been run against real filings. See [LIMITATIONS.md](LIMITATIONS.md).

## Try it

| | What you get | How |
|---|---|---|
| **Static demo** (hosted) | The real FINN screens with the bundled demo data: brief, alerts and rules, portfolio, five research reports with sources, credibility tracker, ticker search. Ask FINN and on-demand research are disabled, because no engine runs there. | <https://claude.ai/artifact/L9dgVoqU59h9e4vsqhg1n1> (a claude.ai page, private until the owner shares it). The published files passed 58/58 checks locally; the URL itself has not been opened from the build environment. |
| **Full app, local** | Everything, including Ask FINN and on-demand research (live NSE/BSE when your network allows) | See below; about 5 minutes |
| **Full app, container** | The same, as one image | `Dockerfile` (see [Deploy](#deploy)) |

### Run locally

Requires Python ≥ 3.11 and Node ≥ 20.

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e "engine[dev]"
(cd apps/web && npm ci && npx next build)
./deploy/start.sh                 # builds the demo data if missing, starts the engine (127.0.0.1:8787) and the web app (:3000)
# open http://localhost:3000       health: http://localhost:3000/api/health
```

Or run the two processes yourself:

```bash
cd engine && python -m finn_engine fixtures && python -m finn_engine research-fixtures   # demo data
python -m finn_engine serve --port 8787                                                    # research engine + Ask FINN
cd apps/web && FINN_ENGINE_URL=http://127.0.0.1:8787 npx next start -p 3000
```

Without `FINN_ENGINE_URL`, the web app still serves the push brief and the already-built reports read-only. Ask FINN and on-demand research then say they need the engine.

### Deploy

`Dockerfile` builds one image: Next.js build, Python engine, and the demo data generated at build time. `deploy/start.sh` runs the engine on 127.0.0.1 and the web app on `$PORT`. It exits if either process dies, so the platform restarts it. `GET /api/health` reports feed, reports and engine reachability, and is the image's health check.

```bash
cp .env.example .env
docker compose up --build          # or: docker build -t finn . && docker run -p 3000:3000 --env-file .env finn
```

Any host that runs a Dockerfile works, for example Render, Railway, Fly.io or Cloud Run. Set `FINN_ENGINE_TOKEN` if the engine could ever be reachable beyond localhost.

**Status:** the image definition has **not** been built here, because Docker Hub is blocked in the build sandbox. The same steps (clean clone → `pip install` → `npm ci` → `next build` → `deploy/start.sh`) were run outside Docker, and the full browser suite passed against the result. See [TESTING.md](TESTING.md).

### Environment variables

| Variable | Used by | Default | Meaning |
|---|---|---|---|
| `PORT` | web | 3000 | Public port |
| `FINN_ENGINE_URL` | web | set by `start.sh` | Where the research engine is; unset = read-only mode |
| `FINN_ENGINE_TOKEN` | web + engine | empty | Shared secret. The engine then requires `Authorization: Bearer …` on everything but `/health` |
| `FINN_FEED_PATH`, `FINN_RESEARCH_DIR` | web | `apps/web/data/…` | Where the web app reads the feed and reports |
| `FINN_NO_LIVE` | engine | 0 | 1 = never fetch NSE/BSE; only the demo companies can be researched |
| `GEMINI_API_KEY` + `FINN_EXPLAIN_MODEL` | engine | empty | Optional model wording for explanations and Ask FINN. Both must be set; output is still checked against the evidence and dropped if it adds anything |
| `FINN_REBUILD_FIXTURES` | `start.sh` | 0 | 1 = regenerate the demo data on start |

**Database.** The push pipeline keeps runs, fetch logs, announcements, events and price bars in SQLite (`data/fixture.db` or `data/live.db`). The schema is created on first connect and re-runs are idempotent upserts. The web app reads only the JSON files the engine writes (`apps/web/data/feed.json`, `apps/web/data/research/*.json`), so it needs no database connection.

## Repository

```
engine/            Python: push pipeline, Pull research, Ask FINN, credibility, research HTTP service, 251 tests
  finn_engine/       sources (BSE, NSE, Yahoo), extract, classify, dedupe, materiality, market, research/…
  RESEARCH.md        Pull research in depth: sections, ledger rules, Ask FINN, credibility
apps/web/          Next.js 15 app (App Router, Tailwind 4); /api/v1/* proxies the engine or reads built files
static-demo/       Hash-routed build of the same screens for static hosting (no engine)
deploy/start.sh    Production start script (both processes)
eval/              Evaluation suite: gold sets, independent re-checks, results (EVAL.md)
qa/                Playwright journey suites
```

## Documentation

| Document | Contents |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Components, data flow, data sources, AI model choices |
| [DECISIONS.md](DECISIONS.md) | Engineering trade-offs and why |
| [TESTING.md](TESTING.md) | What is tested, how to run it, latest results |
| [LIMITATIONS.md](LIMITATIONS.md) | What doesn't work or hasn't been verified |
| [EVAL.md](EVAL.md) | Evaluation report: data integrity, research quality, push intelligence, product, AI reliability |
| [REVIEW.md](REVIEW.md) | Independent code review: findings by severity, and what was fixed |
| [DEMO.md](DEMO.md) | Five-minute demo walkthrough |
| [engine/RESEARCH.md](engine/RESEARCH.md), [engine/README.md](engine/README.md) | Engine internals |

## AI build history

FINN was built in conversation with Claude Code (Anthropic). The genuine development history is that session:
<https://claude.ai/code/session_01BSDCbLwzQYPwCqEmhCKEsE>. [BUILD_HISTORY.md](BUILD_HISTORY.md) summarises the phases and points to the evidence each one left in this repository. It is a summary, not a transcript.
