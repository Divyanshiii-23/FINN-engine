# FINN web

Mobile-first frontend for FINN: the brief, portfolio, research terminal and alerts.

```bash
npm install
npm run dev        # http://localhost:3000
npm run build && npm start
```

## Data in this build

- **Brief, Alerts, Portfolio, event and move pages** read the engine's feed (`data/feed.json`, served by `/api/v1/feed`;
  override the path with `FINN_FEED_PATH`). Generate it with `python -m finn_engine fixtures` (synthetic, labelled
  "Test fixtures" on every screen) or `python -m finn_engine run` (live). See `../../engine/README.md`.
- If the engine runs with `FINN_ENGINE_TOKEN`, set the same variable for the web app; it is sent server-side only.
- **Research** reads Pull research reports (schema `finn.research.v1`). With `FINN_ENGINE_URL` set (e.g.
  `http://127.0.0.1:8787`, from `python -m finn_engine serve`), any NSE ticker can be researched on demand from the page;
  without it, `/api/v1/research/*` serves reports already built in `data/research/` (`python -m finn_engine research SYMBOL`
  or `research-fixtures`) and explains how to build others. Ticker search uses the engine, or `data/research/securities.json`.
  Synthetic test companies are labelled on every research screen. See `../../engine/RESEARCH.md`.

## Structure

| Path | What it is |
| --- | --- |
| `app/` | Routes: `/`, `/portfolio`, `/research`, `/research/[symbol]`, `/research/[symbol]/credibility`, `/alerts` (inbox, rules, sources), `/events/[id]`, `/moves/[symbol]`; API: `/api/v1/feed`, `/api/v1/research[/SYMBOL[/job \| /doc/DOC]]`, `/api/v1/ask/SYMBOL`, `/api/v1/securities`, `/api/health` |
| `components/shell` | App shell: side rail (wide), top bar and bottom tabs (phone) |
| `components/ui` | Design-system primitives: info-class tags, verdicts, sourced values, segmented control, stepper, switch, sheet, sparkline |
| `components/brief`, `portfolio`, `research`, `alerts` | Screens and their parts |
| `lib/push.ts` | Read-time logic over the feed: category rules (hard floors win), windowed brief, alert thresholds |
| `lib/feed.ts` | Feed types and client hook |
| `lib/research.ts` | Research report types, hooks (report, job polling, ticker search) and the evidence registry the source sheet reads |
| `lib/server/research.ts` | Server side: proxy to the engine, or read built reports from disk |
| `components/research` | Research home, company page, the eight sections, Narrative vs Numbers, sources |
| `lib/store.tsx` | Per-device state (rules, triage, read alerts, last looked), persisted to `localStorage` |
| `lib/demo/companies.ts` | The fixture feed's reference times ("now", "last looked") used before a device has its own |

## Visual grammar

- **Amber rule**: needs attention (an alert, or a filing ranked to interrupt).
- **Square**: reported figure. **Triangle**: management guidance. **Hollow square**: management said (checked). **Italic f**: FINN computed.
- **Serif text behind a dotted rule, with a diamond**: FINN analysis (AI). The serif is used nowhere else.
- **Dotted underline**: the value opens its source.
- **Left rule, sans text**: management's own words, with document, page, section and speaker underneath. Quotes are never set in the serif.
