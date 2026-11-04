import { readFile } from "node:fs/promises";
import path from "node:path";

// Serves the push-intelligence feed written by the engine (finn_engine.export).
// The web tier never scrapes: it only reads what the pipeline produced.
export const dynamic = "force-dynamic";

export async function GET() {
  const file = process.env.FINN_FEED_PATH ?? path.join(process.cwd(), "data", "feed.json");
  try {
    const body = await readFile(file, "utf8");
    const feed = JSON.parse(body);
    if (feed?.schema !== "finn.push.v1") {
      return Response.json({ error: { code: "BAD_FEED", message: "Feed file has an unknown schema.", retryable: false } }, { status: 500 });
    }
    return new Response(body, { headers: { "content-type": "application/json", "cache-control": "no-store" } });
  } catch (e) {
    const missing = (e as NodeJS.ErrnoException)?.code === "ENOENT";
    return Response.json(
      {
        error: missing
          ? { code: "NO_FEED", message: "No feed has been generated yet. Run the engine: python -m finn_engine run (or fixtures).", retryable: true }
          : { code: "BAD_FEED", message: "The feed file could not be read.", retryable: true },
      },
      { status: missing ? 404 : 500 },
    );
  }
}
