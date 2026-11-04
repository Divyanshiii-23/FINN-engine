"use client";

import { useEffect, useMemo, useState } from "react";
import { DOC_KIND, docHref, type Passage, type RDoc, type SourceTarget } from "@/lib/research";
import { dayIST } from "@/lib/format";
import { Sheet } from "../ui/Sheet";

/** Opens a document at a page or passage, and pages through it. Mounted once in the app shell. */
export function SourceViewer() {
  const [t, setT] = useState<SourceTarget | null>(null);
  const [data, setData] = useState<{ document: RDoc; passages: Passage[] } | null>(null);
  const [page, setPage] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const on = (e: Event) => {
      const d = (e as CustomEvent<SourceTarget>).detail;
      setT(d);
      setPage(d.page ?? null);
      setError(null);
    };
    window.addEventListener("finn:open-source", on);
    return () => window.removeEventListener("finn:open-source", on);
  }, []);

  useEffect(() => {
    if (!t) return;
    let live = true;
    setData(null);
    fetch(`/api/v1/research/${encodeURIComponent(t.symbol)}/doc/${encodeURIComponent(t.docId)}`, { cache: "no-store" })
      .then((r) => r.json().then((b) => ({ ok: r.ok, b })))
      .then(({ ok, b }) => {
        if (!live) return;
        if (!ok) return setError(b?.error?.message ?? "Couldn't open the document.");
        setData(b);
        if (t.passageId && !t.page) setPage(b.passages.find((p: Passage) => p.id === t.passageId)?.page ?? 1);
        else if (!t.page) setPage(b.passages[0]?.page ?? 1);
      })
      .catch(() => live && setError("Couldn't open the document."));
    return () => {
      live = false;
    };
  }, [t]);

  const pages = useMemo(() => Array.from(new Set((data?.passages ?? []).map((p) => p.page))).sort((a, b) => a - b), [data]);
  const here = (data?.passages ?? []).filter((p) => p.page === page);
  const idx = page ? pages.indexOf(page) : -1;
  const d = data?.document;
  const href = docHref(d, page);

  return (
    <Sheet open={Boolean(t)} onClose={() => setT(null)} title="Document">
      {error ? (
        <p className="text-sm text-down">{error}</p>
      ) : !d ? (
        <p className="text-sm text-ink-3" aria-busy="true">Opening…</p>
      ) : (
        <div className="space-y-4">
          <div className="space-y-0.5">
            <p className="text-sm text-ink">{d.title}</p>
            <p className="text-xs text-ink-2">
              {DOC_KIND[d.kind]}
              {d.period ? `, ${d.period}` : ""}
              {d.filed_at ? `. Filed ${dayIST(d.filed_at)} ${new Date(d.filed_at).getFullYear()}` : ""}
            </p>
          </div>
          <div className="flex items-center justify-between gap-2">
            <button type="button" disabled={idx <= 0} onClick={() => setPage(pages[idx - 1])} className="h-8 rounded-md border border-line px-2.5 text-xs text-ink-2 hover:border-brass/60 disabled:opacity-40">
              ‹ Page {idx > 0 ? pages[idx - 1] : ""}
            </button>
            <label className="flex items-center gap-1.5 text-xs text-ink-3">
              Page
              <select value={page ?? ""} onChange={(e) => setPage(Number(e.target.value))} className="num h-8 rounded-md border border-line bg-base px-1.5 text-xs text-ink">
                {pages.map((p) => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
              <span className="num">of {d.pages ?? pages.at(-1)}</span>
            </label>
            <button type="button" disabled={idx < 0 || idx >= pages.length - 1} onClick={() => setPage(pages[idx + 1])} className="h-8 rounded-md border border-line px-2.5 text-xs text-ink-2 hover:border-brass/60 disabled:opacity-40">
              Page {idx >= 0 && idx < pages.length - 1 ? pages[idx + 1] : ""} ›
            </button>
          </div>
          <ol className="space-y-3">
            {here.map((p) => (
              <li key={p.id} className={`rounded-md border p-3 ${p.id === t?.passageId ? "border-brass/70 bg-brass/5" : "border-line"}`}>
                <p className="mb-1 text-2xs text-ink-3">
                  {[p.section, p.speaker].filter(Boolean).join(" · ")}
                  {p.id === t?.passageId && <span className="ml-1.5 text-brass">cited</span>}
                </p>
                {p.question && <p className="mb-1.5 text-2xs italic text-ink-3">In answer to {p.question.slice(0, 220)}{p.question.length > 220 ? "…" : ""}</p>}
                {p.table ? (
                  <ul className="num space-y-0.5 text-[11px] leading-snug text-ink-2">
                    {p.text.split(" | ").map((row, i) => (
                      <li key={i}>{row}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm leading-relaxed text-ink">{p.text}</p>
                )}
              </li>
            ))}
            {here.length === 0 && <p className="text-sm text-ink-3">No readable text on this page.</p>}
          </ol>
          <p className="border-t border-line pt-3 text-xs text-ink-3">
            {href ? (
              <a href={href} target="_blank" rel="noreferrer" className="text-brass hover:underline">Open the filing at page {page} ↗</a>
            ) : d.fixture ? (
              "Synthetic test document: fictional company, so there is no exchange filing to open."
            ) : (
              "No public link was recorded for this document."
            )}
          </p>
        </div>
      )}
    </Sheet>
  );
}
