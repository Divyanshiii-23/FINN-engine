import { ENGINE, engine, err, readJson, symbolOf } from "@/lib/server/research";

export const dynamic = "force-dynamic";

type Doc = { id: string };
type Passage = { doc_id: string; page: number; id: string };

// A document's passages by page, for source navigation. Works without the engine from the built files.
export async function GET(_req: Request, { params }: { params: Promise<{ symbol: string; doc: string }> }) {
  const p = await params;
  const sym = symbolOf(p.symbol);
  const docId = decodeURIComponent(p.doc);
  if (!sym || !/^d:[0-9a-f]{6,16}$/.test(docId)) return err(400, "BAD_REQUEST", "Unknown document.");
  if (ENGINE) {
    const r = await engine(`/v1/research/${encodeURIComponent(sym)}/doc/${encodeURIComponent(docId)}`);
    if (r.ok) return new Response(await r.text(), { headers: { "content-type": "application/json", "cache-control": "no-store" } });
  }
  const rep = await readJson<{ documents: Doc[] }>(`${sym}.json`);
  const ps = await readJson<Passage[]>(`${sym}.passages.json`);
  const doc = rep?.documents.find((d) => d.id === docId);
  if (!doc || !ps) return err(404, "NO_DOCUMENT", "That document isn't in the report.");
  return Response.json(
    { document: doc, passages: ps.filter((x) => x.doc_id === docId).sort((a, b) => a.page - b.page || a.id.localeCompare(b.id)) },
    { headers: { "cache-control": "no-store" } },
  );
}
