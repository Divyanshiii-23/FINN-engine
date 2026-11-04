import { ENGINE, engine, readJson } from "@/lib/server/research";

export const dynamic = "force-dynamic";

type Row = { symbol: string; name: string; isin: string; series: string; fixture: boolean; list?: string };
let cache: Row[] | null = null;

// Same ranking as the engine's search: exact symbol, symbol prefix, name prefix, then contains.
function search(rows: Row[], raw: string, limit = 12): Row[] {
  // Accept pasted forms: "NSE:INFY", "TCS.NS", "RELIANCE.BO".
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

export async function GET(req: Request) {
  const q = new URL(req.url).searchParams.get("q") ?? "";
  if (ENGINE) {
    const r = await engine(`/v1/securities?q=${encodeURIComponent(q)}`);
    if (r.ok) return new Response(await r.text(), { headers: { "content-type": "application/json", "cache-control": "no-store" } });
  }
  cache ??= (await readJson<{ rows: Row[] }>("securities.json"))?.rows ?? [];
  return Response.json({ results: search(cache, q), source: "static list" }, { headers: { "cache-control": "no-store" } });
}
