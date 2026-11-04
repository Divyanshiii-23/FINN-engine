# Static demo build

The real FINN screens (`apps/web/components`) for a static host with no server.

* `src/routes.ts`: app paths ↔ hash names (`/research/HALCYON` ↔ `#research-HALCYON`; `&` is written `--`)
* `src/shims/`: stand-ins for `next/link` and `next/navigation`
* `src/api.ts`: answers `/api/v1/*` from the bundled JSON, with the same responses the real routes give without an engine. Ask FINN and on-demand research return `503 ENGINE_NOT_CONFIGURED`, and the screens say so.

```bash
(cd ../apps/web && npx next build)   # its CSS is reused, fonts inlined
npm ci && node build.mjs              # -> dist/: index.html, app.js, app.css, data/
python3 -m http.server -d dist 4000  # http://localhost:4000
```

Search uses `data/research/securities.csv`: symbol and name for the NSE EQ series (Nov 2023 seed copy) plus the demo companies.
