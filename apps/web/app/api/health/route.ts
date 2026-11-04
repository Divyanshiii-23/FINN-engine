import { readFile } from "node:fs/promises";
import path from "node:path";
import { ENGINE, engine, readJson } from "@/lib/server/research";

export const dynamic = "force-dynamic";

// Liveness plus what the app can actually serve: used by the container health check and the deploy smoke test.
export async function GET() {
  const file = process.env.FINN_FEED_PATH ?? path.join(process.cwd(), "data", "feed.json");
  let feed: { dataset?: string; as_of?: string; events?: unknown[] } | null = null;
  try {
    feed = JSON.parse(await readFile(file, "utf8"));
  } catch {
    feed = null;
  }
  const index = await readJson<{ companies?: unknown[] }>("index.json").catch(() => null);
  const engineOk = ENGINE ? (await engine("/health")).ok : null;
  return Response.json(
    {
      ok: Boolean(feed),
      feed: feed ? { dataset: feed.dataset, as_of: feed.as_of, events: feed.events?.length ?? 0 } : null,
      research_reports: index?.companies?.length ?? 0,
      engine: ENGINE ? { configured: true, reachable: engineOk } : { configured: false },
    },
    { status: feed ? 200 : 503, headers: { "cache-control": "no-store" } },
  );
}
