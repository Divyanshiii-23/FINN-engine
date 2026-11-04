"use client";

import { useState } from "react";
import { factOf, type Lane } from "@/lib/research";
import { useStore } from "@/lib/store";
import { Segmented } from "../ui/primitives";
import { useWidth } from "./useWidth";
import { CHANGE } from "./NarrativeVsNumbers";
import { Fv, Verdict } from "./report-ui";

const DAY = 86_400_000;
const t = (iso: string) => new Date(iso + (iso.length === 10 ? "T00:00:00Z" : "")).getTime();
const KEPT = new Set(["delivered", "ahead", "consistent"]);

/**
 * One metric, one time axis. Management's target band runs from the day it was
 * stated to the end of its period (a revision starts a new step); the reported
 * path runs underneath; the period's outcome sits at the period end.
 */
export function LaneChart({ lane }: { lane: Lane }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const { openEvidence } = useStore();
  const [view, setView] = useState<"chart" | "list">("chart");
  const pct = lane.unit === "pct";
  const fmt = (v: number) => (pct ? `${v.toFixed(Math.abs(v) < 10 ? 1 : 0)}%` : `₹${Math.round(v).toLocaleString("en-IN")}`);

  const bands = lane.statements.filter((s) => s.band && s.band.kind !== "delta" && s.band.kind !== "multiple");
  const marks = lane.statements.filter((s) => !s.band);
  const dates = [
    ...lane.statements.flatMap((s) => [t(s.date), s.until ? t(s.until) : null, s.period_end ? t(s.period_end) : null]),
    ...lane.actuals.map((a) => t(a.date)),
  ].filter((x): x is number => x !== null);
  const vals = [
    ...bands.flatMap((s) => [s.band!.low, s.band!.high]).filter((v): v is number => v !== null && v !== undefined),
    ...lane.actuals.map((a) => a.value),
    ...lane.outcomes.map((o) => o.value),
  ];
  if (!dates.length) return null;
  const x0 = Math.min(...dates) - 20 * DAY;
  const x1 = Math.max(...dates) + 20 * DAY;
  let lo = vals.length ? Math.min(...vals) : 0;
  let hi = vals.length ? Math.max(...vals) : 1;
  const pad = (hi - lo || Math.abs(hi) || 1) * 0.18;
  lo -= pad;
  hi += pad;
  if (!pct && lo > 0 && lo < (hi - lo) * 0.6) lo = 0;

  const padL = 52, padR = 10, top = 8, plotH = 150, strip = 22;
  const W = Math.max(300, width);
  const plotW = W - padL - padR;
  const X = (ms: number) => padL + ((ms - x0) / (x1 - x0)) * plotW;
  const Y = (v: number) => top + (1 - (v - lo) / (hi - lo)) * plotH;
  const H = top + plotH + strip + 18;
  const baseY = top + plotH + 12;

  // Fiscal year boundaries (31 March) for orientation.
  const years: { x: number; label: string }[] = [];
  for (let y = new Date(x0).getUTCFullYear(); y <= new Date(x1).getUTCFullYear() + 1; y++) {
    const ms = Date.UTC(y, 2, 31);
    if (ms > x0 && ms < x1) years.push({ x: X(ms), label: `FY${String(y % 100).padStart(2, "0")}` });
  }
  // Year-to-date and full-year figures aren't one series: show them as points, not a line.
  const connect = !lane.actuals.some((a) => a.kind === "ytd");
  const path = lane.actuals.filter((a) => a.kind !== "context");
  const ctx = lane.actuals.filter((a) => a.kind === "context");
  const line = (pts: typeof path) => pts.map((a, i) => `${i ? "L" : "M"}${X(t(a.date)).toFixed(1)} ${Y(a.value).toFixed(1)}`).join("");
  const ticks = [lo + pad * 0.5, (lo + hi) / 2, hi - pad * 0.5];

  const open = (id?: string | null) => id && openEvidence(id);
  const key = (e: React.KeyboardEvent, id?: string | null) => (e.key === "Enter" || e.key === " ") && open(id);

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-medium text-ink">{lane.label}</h3>
        <Segmented value={view} onChange={setView} label={`${lane.label}: chart or list`} size="sm" options={[{ value: "chart", label: "Timeline" }, { value: "list", label: "List" }]} />
      </div>
      {!lane.checkable && <p className="text-2xs text-ink-3">Not checkable: {lane.reason}</p>}
      {view === "chart" ? (
        <div ref={ref}>
          <svg width={W} height={H} role="img" aria-label={`${lane.label}: management's targets and the reported path over time`} className="block max-w-full overflow-visible">
            {years.map((y) => (
              <g key={y.label}>
                <line x1={y.x} x2={y.x} y1={top} y2={baseY + 6} className="stroke-line" strokeDasharray="2 3" />
                <text x={y.x - 4} y={H - 2} textAnchor="end" className="num fill-ink-3 text-[10px]">{`${y.label} end`}</text>
              </g>
            ))}
            {ticks.map((v, i) => (
              <g key={i}>
                <line x1={padL} x2={padL + plotW} y1={Y(v)} y2={Y(v)} className="stroke-line/60" />
                <text x={padL - 6} y={Y(v) + 3} textAnchor="end" className="num fill-ink-3 text-[10px]">{fmt(v)}</text>
              </g>
            ))}
            {/* explicit guidance: bands */}
            {bands.map((s, i) => {
              const b = s.band!;
              const xa = X(t(s.date)), xb = X(t(s.until ?? s.period_end ?? s.date));
              const yHi = b.high !== null && b.high !== undefined ? Y(b.high) : top;
              const yLo = b.low !== null && b.low !== undefined ? Y(b.low) : top + plotH;
              const open_ = b.kind === "floor" || b.kind === "ceiling";
              return (
                <g key={i} role="button" tabIndex={0} aria-label={`Guided ${s.target} for ${s.period}, stated ${s.date}`} onClick={() => open(s.fact)} onKeyDown={(e) => key(e, s.fact)} className="cursor-pointer outline-none [&:focus-visible>rect]:stroke-brass">
                  <title>{`${s.call ?? s.date}: ${CHANGE[s.change]?.label ?? s.change} ${s.target ?? ""} for ${s.period}`}</title>
                  <rect x={xa} y={Math.min(yHi, yLo)} width={Math.max(2, xb - xa)} height={Math.max(2, Math.abs(yLo - yHi))}
                    className={s.change === "differs" ? "fill-down/10 stroke-down/50" : "fill-guided/15 stroke-guided/50"} strokeWidth={1} strokeDasharray={open_ ? "3 2" : undefined} />
                  <path d={`M${xa - 4} ${Math.min(yHi, yLo) - 7} L${xa + 4} ${Math.min(yHi, yLo) - 3} L${xa - 4} ${Math.min(yHi, yLo) + 1} Z`} className="fill-guided" />
                </g>
              );
            })}
            {/* qualitative statements and silences, on the strip under the plot */}
            <line x1={padL} x2={padL + plotW} y1={baseY} y2={baseY} className="stroke-line" />
            {marks.map((s, i) => {
              const xm = X(t(s.date));
              const silent = s.kind === "silence";
              return (
                <g key={i} role="button" tabIndex={s.fact ? 0 : -1} aria-label={`${CHANGE[s.change]?.label ?? s.change} on ${s.call ?? s.date}`} onClick={() => open(s.fact)} onKeyDown={(e) => key(e, s.fact)} className={s.fact ? "cursor-pointer outline-none" : ""}>
                  <title>{`${s.call ?? s.date}: ${CHANGE[s.change]?.label ?? s.change}${s.target ? ` ${s.target}` : ""} (${s.period})`}</title>
                  {silent ? (
                    <path d={`M${xm - 3.5} ${baseY - 3.5} L${xm + 3.5} ${baseY + 3.5} M${xm + 3.5} ${baseY - 3.5} L${xm - 3.5} ${baseY + 3.5}`} className="stroke-alert" strokeWidth={1.6} />
                  ) : (
                    <path d={`M${xm - 4} ${baseY - 5} L${xm + 4} ${baseY} L${xm - 4} ${baseY + 5} Z`} className="fill-base stroke-guided" strokeWidth={1.3} />
                  )}
                </g>
              );
            })}
            {/* reported path */}
            {ctx.length > 1 && <path d={line(ctx)} fill="none" className="stroke-ink-3" strokeWidth={1} strokeDasharray="3 3" />}
            {connect && path.length > 1 && <path d={line(path)} fill="none" className="stroke-ink-3" strokeWidth={1.25} />}
            {[...path, ...ctx].map((a) => (
              <g key={a.fact} role="button" tabIndex={0} aria-label={`${factOf(a.fact)?.label}: ${factOf(a.fact)?.display}`} onClick={() => open(a.fact)} onKeyDown={(e) => key(e, a.fact)} className="cursor-pointer outline-none [&:hover>rect]:fill-ink [&:focus-visible>rect]:stroke-brass">
                <title>{`${factOf(a.fact)?.label}: ${factOf(a.fact)?.display}`}</title>
                <rect x={X(t(a.date)) - 2.5} y={Y(a.value) - 2.5} width={5} height={5} rx={0.5} className={a.kind === "context" || a.kind === "ytd" ? "fill-base stroke-ink-3" : "fill-ink-2"} strokeWidth={1} />
              </g>
            ))}
            {/* outcome at the period end */}
            {lane.outcomes.map((o) => {
              const unscored = o.verdict === "unverifiable";
              const cls = unscored ? "fill-none stroke-ink-3" : !o.closed ? "fill-base stroke-ink-2" : KEPT.has(o.verdict) ? "fill-up stroke-up" : "fill-down stroke-down";
              const xo = X(t(o.date));
              return (
                <g key={o.ledger} role="button" tabIndex={0} aria-label={`${o.period} outcome: ${factOf(o.fact)?.display}, ${o.verdict}`} onClick={() => open(o.fact)} onKeyDown={(e) => key(e, o.fact)} className="cursor-pointer outline-none">
                  <title>{`${o.period}${o.ytd ? ` (${o.ytd} so far)` : ""}: ${factOf(o.fact)?.display}, ${o.verdict}`}</title>
                  {unscored ? (
                    <circle cx={xo} cy={Y(o.value)} r={5} className={cls} strokeWidth={1.5} strokeDasharray="2 1.5" />
                  ) : (
                    <rect x={xo - 5} y={Y(o.value) - 5} width={10} height={10} rx={1} className={cls} strokeWidth={1.75} />
                  )}
                </g>
              );
            })}
          </svg>
          <p className="mt-1 text-2xs text-ink-3">
            Bands: management&apos;s explicit range from the day it was said to the end of its period. Grey squares: reported path. Large squares: the period&apos;s outcome
            (green kept, red missed, hollow: year to date, still open); dashed circle: the actual beside a worded target, not scored. Hollow triangles: qualitative statements; ✕: not repeated or withdrawn.
          </p>
        </div>
      ) : (
        <LaneList lane={lane} />
      )}
    </div>
  );
}

function LaneList({ lane }: { lane: Lane }) {
  const { openEvidence } = useStore();
  type Ev = { date: string; kind: "said" | "outcome"; node: React.ReactNode };
  const evs: Ev[] = [
    ...lane.statements.map((s) => ({
      date: s.date,
      kind: "said" as const,
      node: (
        <span className="flex flex-wrap items-baseline gap-x-2">
          <span className={`text-xs font-medium ${CHANGE[s.change]?.cls ?? "text-ink-2"}`}>{CHANGE[s.change]?.label ?? s.change}</span>
          {s.target && <span className="num text-xs text-guided">{s.target}</span>}
          <span className="text-2xs text-ink-3">for {s.period}, {s.call ?? ""}</span>
          {s.fact && (
            <button type="button" onClick={() => openEvidence(s.fact!)} className="inline-flex min-h-6 items-center text-2xs text-brass hover:underline">
              quote, p.{factOf(s.fact)?.page}
            </button>
          )}
        </span>
      ),
    })),
    ...lane.outcomes.map((o) => ({
      date: o.date,
      kind: "outcome" as const,
      node: (
        <span className="flex flex-wrap items-baseline gap-x-2">
          <span className="text-xs text-ink-2">{o.closed ? `${o.period} reported` : `${o.ytd ?? o.period} so far`}</span>
          <Fv id={o.fact} className="text-xs" />
          <Verdict v={o.verdict} note={o.status_note} />
        </span>
      ),
    })),
  ].sort((a, b) => a.date.localeCompare(b.date));
  return (
    <ol className="space-y-1.5 border-l border-line pl-3">
      {evs.map((e, i) => (
        <li key={i} className="relative">
          <span aria-hidden className={`absolute -left-[15.5px] top-1.5 h-1.5 w-1.5 ${e.kind === "outcome" ? "bg-ink-2" : "rotate-45 bg-guided"}`} />
          <span className="num mr-2 text-2xs text-ink-3">{e.date}</span>
          {e.node}
        </li>
      ))}
    </ol>
  );
}
