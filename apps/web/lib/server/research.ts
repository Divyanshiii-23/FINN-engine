import { readFile } from "node:fs/promises";
import path from "node:path";

// Server-side access to Pull research. With FINN_ENGINE_URL set, requests go
// to the engine's research service (finn serve); otherwise reports already
// built on disk (finn research / research-fixtures) are served read-only.

export const ENGINE = process.env.FINN_ENGINE_URL?.replace(/\/$/, "") || null;
const DIR = process.env.FINN_RESEARCH_DIR ?? path.join(process.cwd(), "data", "research");
const SYMBOL = /^[A-Z0-9][A-Z0-9&-]{0,19}$/;

export function symbolOf(raw: string): string | null {
  const s = decodeURIComponent(raw).trim().toUpperCase().replace(/\.NS$/, "").replace(/^NSE:/, "");
  return SYMBOL.test(s) ? s : null;
}

export function err(status: number, code: string, message: string, extra: Record<string, unknown> = {}) {
  return Response.json({ error: { code, message }, ...extra }, { status, headers: { "cache-control": "no-store" } });
}

const TOKEN = process.env.FINN_ENGINE_TOKEN || null;

export async function engine(pathname: string, init?: RequestInit): Promise<Response> {
  try {
    const headers = new Headers(init?.headers);
    if (TOKEN) headers.set("authorization", `Bearer ${TOKEN}`); // server-side only; never sent to the browser
    const r = await fetch(`${ENGINE}${pathname}`, { cache: "no-store", ...init, headers, signal: AbortSignal.timeout(15000) });
    return r;
  } catch {
    return err(502, "ENGINE_UNREACHABLE", "The research engine isn't responding. Check that `finn serve` is running.", { engine: true });
  }
}

export async function readJson<T>(name: string): Promise<T | null> {
  try {
    return JSON.parse(await readFile(path.join(DIR, name), "utf8")) as T;
  } catch (e) {
    if ((e as NodeJS.ErrnoException)?.code === "ENOENT") return null;
    throw e;
  }
}

export const NO_ENGINE =
  "On-demand research needs the engine. Run `python -m finn_engine research SYMBOL` to build a report, or start `python -m finn_engine serve` and set FINN_ENGINE_URL.";

/** Relays an engine response, normalising its error shape to {error: {code, message}}. */
export async function relay(r: Response): Promise<Response> {
  const body = (await r.json().catch(() => null)) as Record<string, unknown> | null;
  const h = { "content-type": "application/json", "cache-control": "no-store" };
  if (r.ok) return new Response(JSON.stringify(body ?? {}), { status: r.status, headers: h });
  const e = body?.error;
  const norm = typeof e === "string" ? { ...body, error: { code: e, message: String(body?.message ?? "The research engine returned an error.") } } : body ?? { error: { code: "ENGINE_ERROR", message: `The research engine returned ${r.status}.` } };
  return new Response(JSON.stringify(norm), { status: r.status, headers: h });
}
