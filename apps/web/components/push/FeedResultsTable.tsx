"use client";

import { useState } from "react";
import type { FeedFigure, FeedResults } from "@/lib/feed";
import { crore, pct, pp, signClass } from "@/lib/format";
import { Chevron, ClassMark, ClassTag, TextButton } from "../ui/primitives";

function Cell({ f, label }: { f: FeedFigure; label: string }) {
  if (f.value === null) return <span className="text-ink-3">n/a</span>;
  const src = f.evidence?.formula ?? (f.evidence?.text ? `Page ${f.evidence.page}: ${f.evidence.text}` : undefined);
  return (
    <span className="num" title={src} aria-label={src ? `${label} ${crore(f.value)}. Source: ${src}` : undefined}>
      {crore(f.value)}
    </span>
  );
}

export function FeedResultsTable({ r, showChecks = false }: { r: FeedResults; showChecks?: boolean }) {
  const [open, setOpen] = useState(showChecks);
  if (r.status === "failed" || r.status === "unavailable") {
    return (
      <p className="rounded-md border border-line bg-base/60 px-3 py-2 text-xs text-ink-2">
        Figures not extracted: {r.reason}. Open the filing to read them.
      </p>
    );
  }
  const m = r.margin;
  return (
    <div className="rounded-md border border-line bg-base/60">
      <table className="w-full text-sm">
        <caption className="sr-only">Results, rupees crore, {r.basis}</caption>
        <thead>
          <tr className="text-2xs text-ink-3">
            <th scope="col" className="py-1.5 pl-3 text-left font-normal">₹ crore</th>
            <th scope="col" className="py-1.5 text-right font-normal">{r.period_label ?? "This qtr"}</th>
            <th scope="col" className="hidden py-1.5 text-right font-normal sm:table-cell">Prev qtr</th>
            <th scope="col" className="hidden py-1.5 text-right font-normal sm:table-cell">Year ago</th>
            <th scope="col" className="py-1.5 text-right font-normal">QoQ</th>
            <th scope="col" className="py-1.5 pr-3 text-right font-normal">YoY</th>
          </tr>
        </thead>
        <tbody className="border-t border-line">
          {r.rows.map((row) => (
            <tr key={row.key} className="border-b border-line/60 last:border-0">
              <th scope="row" className="py-1.5 pl-3 text-left font-normal text-ink-2">
                <span className="inline-flex items-center gap-1.5">
                  {row.key === "ebitda" ? "EBITDA" : row.key === "revenue" ? "Revenue" : row.key.toUpperCase()}
                  {row.key === "ebitda" && row.current.value !== null && <ClassMark kind="computed" className="text-ink-3" />}
                </span>
              </th>
              <td className="py-1.5 text-right text-ink"><Cell f={row.current} label={row.label} /></td>
              <td className="hidden py-1.5 text-right text-ink-2 sm:table-cell"><Cell f={row.prev_q} label={`${row.label} previous quarter`} /></td>
              <td className="hidden py-1.5 text-right text-ink-2 sm:table-cell"><Cell f={row.prev_y} label={`${row.label} year ago`} /></td>
              <td className={`num py-1.5 text-right ${signClass(row.qoq)}`}>{pct(row.qoq)}</td>
              <td className={`num py-1.5 pr-3 text-right ${signClass(row.yoy)}`}>{pct(row.yoy)}</td>
            </tr>
          ))}
          {m && m.current !== null && (
            <tr>
              <th scope="row" className="py-1.5 pl-3 text-left font-normal text-ink-2">
                <span className="inline-flex items-center gap-1.5">EBITDA margin <ClassMark kind="computed" className="text-ink-3" /></span>
              </th>
              <td className="num py-1.5 text-right">{pct(m.current, 1, false)}</td>
              <td className="num hidden py-1.5 text-right text-ink-2 sm:table-cell">{pct(m.prev_q, 1, false)}</td>
              <td className="num hidden py-1.5 text-right text-ink-2 sm:table-cell">{pct(m.prev_y, 1, false)}</td>
              <td className={`num py-1.5 text-right ${signClass(m.prev_q !== null ? m.current - m.prev_q : null)}`}>{m.prev_q !== null ? pp((m.current - m.prev_q) * 100) : "n/a"}</td>
              <td className={`num py-1.5 pr-3 text-right ${signClass(m.prev_y !== null ? m.current - m.prev_y : null)}`}>{m.prev_y !== null ? pp((m.current - m.prev_y) * 100) : "n/a"}</td>
            </tr>
          )}
        </tbody>
      </table>
      <div className="border-t border-line px-3 py-1.5">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-2xs text-ink-3">
          <ClassTag kind="reported">Extracted from the filing, {r.basis}{r.unit_detected ? `, converted from ₹ ${r.unit_detected}s` : ""}</ClassTag>
          <ClassTag kind="computed">EBITDA, margin, QoQ and YoY computed</ClassTag>
          {r.status === "needs_review" && <span className="text-alert">Needs review: {r.reason}</span>}
        </div>
        <div className="-ml-2 mt-1">
          <TextButton onClick={() => setOpen((v) => !v)} aria-expanded={open}>
            <Chevron open={open} /> How these were extracted
          </TextButton>
        </div>
        {open && (
          <div className="space-y-2 pb-2 text-xs text-ink-2">
            {r.ebitda_formula && <p>EBITDA = {r.ebitda_formula}.</p>}
            <p>
              Page {r.page}. Columns {r.column_order === "header_dates" ? "matched to the header dates" : "assumed in SEBI order (not verified from headers)"}.
            </p>
            <ul className="space-y-1">
              {r.checks.map((c) => (
                <li key={c.check} className="flex gap-2">
                  <span className={c.ok ? "text-up" : "text-alert"} aria-label={c.ok ? "passed" : "failed"}>{c.ok ? "✓" : "!"}</span>
                  <span>
                    {c.check}: <span className="num text-ink-3">{c.detail}</span>
                  </span>
                </li>
              ))}
            </ul>
            <ul className="space-y-1">
              {r.rows.map((row) => (
                <li key={row.key} className="text-ink-3">
                  <span className="text-ink-2">{row.label}: </span>
                  {row.current.evidence?.formula ?? row.current.evidence?.text ?? "not found"}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
