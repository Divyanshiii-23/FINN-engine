import { ENGINE, engine, err, relay, symbolOf } from "@/lib/server/research";

export const dynamic = "force-dynamic";

// Ask FINN runs in the engine, next to the report and its passages. The web tier only relays.
export async function POST(req: Request, { params }: { params: Promise<{ symbol: string }> }) {
  const sym = symbolOf((await params).symbol);
  if (!sym) return err(400, "INVALID_SYMBOL", "That isn't an NSE symbol.");
  const body = (await req.json().catch(() => ({}))) as { question?: string };
  const q = String(body.question ?? "").trim();
  if (!q) return err(400, "EMPTY_QUESTION", "Ask a question about the company.");
  if (q.length > 500) return err(400, "TOO_LONG", "Keep the question under 500 characters.");
  if (!ENGINE)
    return err(503, "ENGINE_NOT_CONFIGURED", "Ask FINN needs the research engine. Start `python -m finn_engine serve` and set FINN_ENGINE_URL, or use `python -m finn_engine ask SYMBOL \"question\"`.");
  const r = await engine(`/v1/ask/${encodeURIComponent(sym)}`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ question: q }) });
  return relay(r);
}
