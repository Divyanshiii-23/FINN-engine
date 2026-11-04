"use client";

import { useState } from "react";
import { docLabel, docOf, factOf, type RGap, type RVerdict } from "@/lib/research";
import { useStore } from "@/lib/store";
import { ClassMark, Segmented, Sourced } from "../ui/primitives";
import { useWidth } from "./useWidth";

/** A figure from the report: shows its display text and opens its source. */
export function Fv({ id, label, empty = "n/a", className = "" }: { id?: string | null; label?: string; empty?: string; className?: string }) {
  const f = factOf(id);
  if (!f) return <span className={`num text-ink-3 ${className}`}>{empty}</span>;
  const tone = f.unit === "growth" || f.unit === "pp" ? (f.value ?? 0) > 0 ? "text-up" : (f.value ?? 0) < 0 ? "text-down" : "" : "";
  return (
    <Sourced id={f.id} label={label ?? f.label} className={`${tone} ${className}`}>
      {(f.display ?? "").replace(/^-/, "−").replace(/^\+/, "+")}
    </Sourced>
  );
}

const VERDICT: Record<RVerdict, { label: string; cls: string }> = {
  delivered: { label: "Delivered", cls: "text-up border-up/40" },
  ahead: { label: "Ahead", cls: "text-up border-up/40" },
  consistent: { label: "Consistent", cls: "text-up border-up/40" },
  missed: { label: "Missed", cls: "text-down border-down/45" },
  contradicted: { label: "Contradicted", cls: "text-down border-down/45" },
  partial: { label: "Partly consistent", cls: "text-alert border-alert/45" },
  dropped: { label: "Dropped", cls: "text-alert border-alert/45" },
  pending: { label: "Pending", cls: "text-ink-2 border-line-strong" },
  unverifiable: { label: "Not checkable", cls: "text-ink-3 border-line-strong" },
};

export function Verdict({ v, note }: { v: RVerdict; note?: string }) {
  const m = VERDICT[v];
  const extra = note && !["words only"].includes(note) ? note : v === "unverifiable" && note === "words only" ? "words only" : null;
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      <span className={`inline-flex h-5 items-center rounded-sm border px-1.5 text-2xs font-medium ${m.cls}`}>{m.label}</span>
      {extra && <span className={`text-2xs ${/behind|at risk|withdrawn/.test(extra) ? "text-alert" : "text-ink-3"}`}>{extra}</span>}
    </span>
  );
}

export function Gaps({ gaps }: { gaps?: RGap[] }) {
  if (!gaps || gaps.length === 0) return null;
  return (
    <ul className="space-y-1">
      {gaps.map((g, i) => (
        <li key={i} className="flex gap-2 text-xs text-ink-3">
          <span aria-hidden className="mt-[5px] h-1 w-1 shrink-0 rounded-full bg-ink-3" />
          <span>{g.detail}</span>
        </li>
      ))}
    </ul>
  );
}

/** A quoted statement with where it was said. */
export function Said({ id, compact = false }: { id?: string | null; compact?: boolean }) {
  const { openEvidence } = useStore();
  const f = factOf(id);
  if (!f?.quote) return null;
  const d = docOf(f.doc_id);
  const where = [d ? docLabel(d) : null, f.page ? `p. ${f.page}` : null, f.section, f.speaker && f.speaker !== "Company document" ? f.speaker.split(",")[0] : null]
    .filter(Boolean)
    .join(" · ");
  return (
    <figure className={compact ? "space-y-0.5" : "space-y-1"}>
      <blockquote className={`border-l-2 border-line-strong pl-2.5 leading-relaxed text-ink ${compact ? "text-[13px]" : "text-sm"}`}>“{f.quote}”</blockquote>
      <figcaption>
        <button type="button" onClick={() => openEvidence(f.id)} className="text-left text-2xs text-ink-3 underline decoration-dotted underline-offset-2 hover:text-brass" aria-label={`Show source: ${where}`}>
          {where}
        </button>
      </figcaption>
    </figure>
  );
}

/** Evidence chips: one per cited fact. */
export function Cites({ ids }: { ids: (string | null | undefined)[] }) {
  const { openEvidence } = useStore();
  const facts = ids.map((i) => factOf(i)).filter((f): f is NonNullable<typeof f> => Boolean(f));
  if (!facts.length) return null;
  return (
    <ul className="flex min-w-0 flex-wrap gap-1.5" aria-label="Evidence">
      {facts.map((f) => (
        <li key={f.id} className="min-w-0 max-w-full">
          <button
            type="button"
            onClick={() => openEvidence(f.id)}
            className="inline-flex h-6 max-w-full items-center sm:max-w-[22rem] gap-1.5 rounded-sm border border-line px-1.5 text-2xs text-ink-2 hover:border-brass/60 hover:text-ink"
          >
            <ClassMark kind={f.info_class} className={f.info_class === "guidance" ? "text-guided" : ""} />
            <span className="truncate">{f.quote ? `${f.label}${f.period ? ` · said ${f.period}` : ""}, p.${f.page}` : f.label}</span>
            {f.display && !f.quote && <span className="num shrink-0 whitespace-nowrap text-ink">{f.display}</span>}
          </button>
        </li>
      ))}
    </ul>
  );
}

// ------------------------------------------------------------------ charts

type Series = { label: string; ids: (string | null)[]; kind: "bars" | "line"; unit: "cr" | "pct" };

/**
 * Small multiples on one quarter axis (never a dual axis). Each mark is a
 * button that opens the figure's source; a table view is one tap away.
 */
export function QuarterCharts({ quarters, series }: { quarters: string[]; series: Series[] }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [view, setView] = useState<"chart" | "table">("chart");
  const { openEvidence } = useStore();
  const n = quarters.length;
  const padL = 50;
  const padR = 8;
  const plotW = Math.max(220, width - padL - padR);
  const step = plotW / Math.max(n, 1);
  const cx = (i: number) => padL + step * i + step / 2;
  const short = (q: string) => (step < 62 ? q.replace(" FY", "’") : q);
  return (
    <div className="space-y-2">
      <div className="flex justify-end">
        <Segmented value={view} onChange={setView} label="Chart or table" size="sm" options={[{ value: "chart", label: "Chart" }, { value: "table", label: "Table" }]} />
      </div>
      {view === "table" ? (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[520px] text-xs">
            <thead>
              <tr className="text-ink-3">
                <th className="py-1.5 text-left font-normal" />
                {quarters.map((q) => (
                  <th key={q} className="num py-1.5 text-right font-normal">{q}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {series.map((s) => (
                <tr key={s.label} className="border-t border-line">
                  <th className="py-1.5 pr-3 text-left font-normal text-ink-2">{s.label}</th>
                  {s.ids.map((id, i) => (
                    <td key={i} className="py-1.5 text-right"><Fv id={id} /></td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div ref={ref} className="space-y-3">
          {series.map((s) => {
            const vals = s.ids.map((id) => factOf(id)?.value ?? null);
            const nums = vals.filter((v): v is number => v !== null);
            if (!nums.length) return null;
            const h = 112;
            const lo = s.kind === "bars" ? Math.min(0, ...nums) : Math.min(...nums) - (Math.max(...nums) - Math.min(...nums) || 0.02) * 0.4;
            const hi = Math.max(...nums) + (s.kind === "line" ? (Math.max(...nums) - Math.min(...nums) || 0.02) * 0.4 : 0);
            const y = (v: number) => 6 + (1 - (v - lo) / (hi - lo || 1)) * (h - 12);
            const fmt = (v: number) => (s.unit === "pct" ? `${(v * 100).toFixed(1)}%` : v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v.toFixed(0));
            const pts = vals.map((v, i) => (v === null ? null : [cx(i), y(v)] as const));
            return (
              <figure key={s.label} className="space-y-1">
                <figcaption className="text-xs text-ink-2">{s.label}</figcaption>
                <svg width={padL + plotW + padR} height={h + 18} role="img" aria-label={`${s.label} by quarter`} className="block max-w-full overflow-visible">
                  {[lo, (lo + hi) / 2, hi].map((t, k) => (
                    <g key={k}>
                      <line x1={padL} x2={padL + plotW} y1={y(t)} y2={y(t)} className="stroke-line" strokeWidth={1} />
                      <text x={padL - 6} y={y(t) + 3} textAnchor="end" className="num fill-ink-3 text-[10px]">{fmt(t)}</text>
                    </g>
                  ))}
                  {s.kind === "line" && (
                    <path
                      d={pts.filter(Boolean).map((p, k) => `${k ? "L" : "M"}${p![0].toFixed(1)} ${p![1].toFixed(1)}`).join("")}
                      fill="none"
                      className="stroke-brass"
                      strokeWidth={1.75}
                    />
                  )}
                  {vals.map((v, i) =>
                    v === null ? null : (
                      <g key={i} role="button" tabIndex={0} aria-label={`${s.label}, ${quarters[i]}: ${factOf(s.ids[i])?.display}`}
                        onClick={() => openEvidence(s.ids[i]!)} onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && openEvidence(s.ids[i]!)}
                        className="cursor-pointer outline-none [&:focus-visible>rect]:stroke-brass [&:hover>rect]:fill-brass/80">
                        <title>{`${quarters[i]}: ${factOf(s.ids[i])?.display}`}</title>
                        {s.kind === "bars" ? (
                          <rect x={cx(i) - Math.min(14, step * 0.3)} width={Math.min(28, step * 0.6)} y={Math.min(y(v), y(0))} height={Math.max(1, Math.abs(y(0) - y(v)))} rx={1.5} className="fill-ink-3" strokeWidth={1.5} />
                        ) : (
                          <>
                            <rect x={cx(i) - step / 2} width={step} y={0} height={h} fill="transparent" strokeWidth={0} />
                            <circle cx={cx(i)} cy={y(v)} r={3.2} className="fill-surface stroke-brass" strokeWidth={1.5} />
                          </>
                        )}
                      </g>
                    ),
                  )}
                  {quarters.map((q, i) => (
                    <text key={q} x={cx(i)} y={h + 14} textAnchor="middle" className="num fill-ink-3 text-[10px]">
                      {n > 6 && step < 46 && i % 2 ? "" : short(q)}
                    </text>
                  ))}
                </svg>
              </figure>
            );
          })}
        </div>
      )}
    </div>
  );
}
