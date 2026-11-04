import { ENGINE, engine, readJson } from "@/lib/server/research";

export const dynamic = "force-dynamic";

export async function GET() {
  if (ENGINE) {
    const r = await engine("/v1/research");
    if (r.ok) return new Response(await r.text(), { headers: { "content-type": "application/json", "cache-control": "no-store" } });
  }
  const idx = (await readJson<{ companies: unknown[] }>("index.json")) ?? { companies: [] };
  return Response.json({ ...idx, engine: Boolean(ENGINE) }, { headers: { "cache-control": "no-store" } });
}
