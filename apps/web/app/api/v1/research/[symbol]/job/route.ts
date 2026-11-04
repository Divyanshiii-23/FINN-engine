import { ENGINE, NO_ENGINE, engine, err, symbolOf } from "@/lib/server/research";

export const dynamic = "force-dynamic";

export async function GET(_req: Request, { params }: { params: Promise<{ symbol: string }> }) {
  const sym = symbolOf((await params).symbol);
  if (!sym) return err(400, "INVALID_SYMBOL", "That isn't an NSE symbol.");
  if (!ENGINE) return err(404, "NO_JOB", NO_ENGINE);
  const r = await engine(`/v1/research/${encodeURIComponent(sym)}/job`);
  return new Response(await r.text(), { status: r.status, headers: { "content-type": "application/json", "cache-control": "no-store" } });
}
