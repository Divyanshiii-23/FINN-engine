import { ENGINE, NO_ENGINE, engine, err, relay, readJson, symbolOf } from "@/lib/server/research";

export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ symbol: string }> };

export async function GET(_req: Request, { params }: Ctx) {
  const sym = symbolOf((await params).symbol);
  if (!sym) return err(400, "INVALID_SYMBOL", "That isn't an NSE symbol (letters, digits, & and - only).");
  if (ENGINE) {
    const r = await engine(`/v1/research/${encodeURIComponent(sym)}`);
    const body = await r.json().catch(() => null);
    if (r.status === 200 && body) return Response.json({ ...body, _engine: true }, { headers: { "cache-control": "no-store" } });
    if (r.status === 404) return Response.json({ error: { code: "NO_REPORT", message: body?.message ?? `No report for ${sym} yet.` }, engine: true, job: body?.job ?? null }, { status: 404 });
    const e = body?.error;
    return Response.json(typeof e === "string" ? { ...body, error: { code: e, message: String(body?.message ?? "The research engine returned an error.") } } : body ?? { error: { code: "ENGINE_ERROR", message: "The research engine returned an error." } }, { status: r.status });
  }
  const rep = await readJson<Record<string, unknown>>(`${sym}.json`);
  if (!rep) return Response.json({ error: { code: "NO_REPORT", message: `No report for ${sym} has been built.` }, engine: false, job: null }, { status: 404 });
  if (rep.schema !== "finn.research.v1") return err(500, "BAD_REPORT", "The report file has an unknown schema.");
  return Response.json({ ...rep, _engine: false }, { headers: { "cache-control": "no-store" } });
}

export async function POST(_req: Request, { params }: Ctx) {
  const sym = symbolOf((await params).symbol);
  if (!sym) return err(400, "INVALID_SYMBOL", "That isn't an NSE symbol (letters, digits, & and - only).");
  if (!ENGINE) return err(503, "ENGINE_NOT_CONFIGURED", NO_ENGINE, { engine: false });
  const r = await engine(`/v1/research/${encodeURIComponent(sym)}`, { method: "POST" });
  return relay(r);
}
