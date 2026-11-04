// The static demo has no server. This answers the app's /api/v1/* requests from the JSON files the
// engine built, exactly as the real routes do when no engine is connected (apps/web/app/api/v1/*):
// same shapes, same status codes, and the engine-only features say they need the engine.

const BASE = new URL("./data/", document.baseURI || location.href); // fixed at load: later history changes can't move it
const SYMBOL = /^[A-Z0-9][A-Z0-9&-]{0,19}$/;
const NO_ENGINE =
  "This is the static demo: the research engine isn't running here, so reports can't be built on demand. Run FINN locally (README) to research any NSE ticker.";
const realFetch = window.fetch.bind(window);
const cache = new Map<string, Promise<unknown>>();

function file<T>(name: string): Promise<T | null> {
  if (!cache.has(name)) cache.set(name, realFetch(new URL(name, BASE)).then((r) => (r.ok ? r.json() : null)).catch(() => null));
  return cache.get(name) as Promise<T | null>;
}

let secRows: Promise<Row[]> | null = null;
function securities(): Promise<Row[]> {
  secRows ??= realFetch(new URL("research/securities.csv", BASE))
    .then((r) => (r.ok ? r.text() : ""))
    .then((t) =>
      t.split("\n").slice(1).filter(Boolean).map((line) => {
        const [symbol, name, fx] = line.split(",");
        return { symbol, name, isin: "", series: "EQ", fixture: fx === "1", list: fx === "1" ? undefined : "NSE equity list, seed copy dated 5 Nov 2023" };
      }),
    )
    .catch(() => []);
  return secRows;
}

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
const err = (status: number, code: string, message: string, extra: Record<string, unknown> = {}) => json({ error: { code, message }, ...extra }, status);

function symbolOf(raw: string): string | null {
  const s = decodeURIComponent(raw).trim().toUpperCase().replace(/\.NS$/, "").replace(/^NSE:/, "");
  return SYMBOL.test(s) ? s : null;
}

type Row = { symbol: string; name: string; isin: string; series: string; fixture: boolean; list?: string };
function search(rows: Row[], raw: string, limit = 12): Row[] {
  const q = raw.trim().toUpperCase().replace(/^(NSE|BSE)\s*:\s*/, "").replace(/\.(NS|BO)$/, "").trim();
  if (!q) return [];
  const rank = (r: Row) => {
    const s = r.symbol.toUpperCase(), n = r.name.toUpperCase();
    return s === q ? 0 : s.startsWith(q) ? 1 : n.startsWith(q) ? 2 : s.includes(q) ? 3 : 4;
  };
  return rows
    .filter((r) => r.symbol.toUpperCase().includes(q) || r.name.toUpperCase().includes(q))
    .sort((a, b) => rank(a) - rank(b) || a.symbol.length - b.symbol.length || a.symbol.localeCompare(b.symbol))
    .slice(0, limit);
}

async function route(url: URL, method: string): Promise<Response> {
  const parts = url.pathname.replace(/^.*\/api\/v1\//, "").split("/").filter(Boolean);
  if (parts[0] === "feed") {
    const f = await file<{ schema?: string }>("feed.json");
    if (!f) return err(404, "NO_FEED", "No feed is bundled with this demo.");
    return json(f);
  }
  if (parts[0] === "securities") {
    return json({ results: search(await securities(), url.searchParams.get("q") ?? ""), source: "static list (NSE EQ series, Nov 2023 copy, plus the demo companies)" });
  }
  if (parts[0] === "ask") {
    if (!symbolOf(parts[1] ?? "")) return err(400, "INVALID_SYMBOL", "That isn't an NSE symbol.");
    return err(503, "ENGINE_NOT_CONFIGURED", "Ask FINN needs the research engine, which this static demo doesn't run. Run FINN locally (README) to ask questions; every answer is built from the report's own passages and checked against them.");
  }
  if (parts[0] === "research") {
    if (parts.length === 1) return json({ ...((await file<object>("research/index.json")) ?? { companies: [] }), engine: false });
    const sym = symbolOf(parts[1]);
    if (!sym) return err(400, "INVALID_SYMBOL", "That isn't an NSE symbol (letters, digits, & and - only).");
    if (parts[2] === "job") return err(404, "NO_JOB", NO_ENGINE);
    if (parts[2] === "doc") {
      const docId = decodeURIComponent(parts[3] ?? "");
      const rep = await file<{ documents: { id: string }[] }>(`research/${sym}.json`);
      const ps = await file<{ doc_id: string; page: number; id: string }[]>(`research/${sym}.passages.json`);
      const doc = rep?.documents.find((d) => d.id === docId);
      if (!doc || !ps) return err(404, "NO_DOCUMENT", "That document isn't in the report.");
      return json({ document: doc, passages: ps.filter((x) => x.doc_id === docId).sort((a, b) => a.page - b.page || a.id.localeCompare(b.id)) });
    }
    if (method === "POST") return err(503, "ENGINE_NOT_CONFIGURED", NO_ENGINE, { engine: false });
    const rep = await file<{ schema?: string }>(`research/${sym}.json`);
    if (!rep) return json({ error: { code: "NO_REPORT", message: `No report for ${sym} is bundled with this static demo.` }, engine: false, job: null }, 404);
    return json({ ...rep, _engine: false });
  }
  if (parts[0] === "health") return json({ ok: true, static: true });
  return err(404, "NOT_FOUND", "Unknown endpoint.");
}

export function installApi() {
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const url = new URL(raw, location.origin);
    if (url.origin === location.origin && /\/api\/v1\//.test(url.pathname)) {
      return route(url, (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase());
    }
    return realFetch(input, init);
  };
}
