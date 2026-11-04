"use client";

import { useState } from "react";
import { DOC_KIND, docOf, factOf, type RClaim, type Report } from "@/lib/research";
import { dayIST } from "@/lib/format";
import { Chevron, ClassTag, SectionHead } from "../ui/primitives";
import { Cites, Fv, Gaps, QuarterCharts, Said, Verdict } from "./report-ui";
import { safeUrl } from "@/lib/safe-url";

// ------------------------------------------------------------------ 1. Business snapshot

export function Business({ r }: { r: Report }) {
  const b = r.sections.business;
  const idn = r.identity;
  return (
    <div className="space-y-4">
      {b.description ? <Said id={b.description} /> : null}
      <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-xs sm:grid-cols-4">
        {[
          ["Industry (BSE)", idn.industry ?? "n/a"],
          ["ISIN", idn.isin ?? "n/a"],
          ["BSE code", idn.bse_code ?? "not found"],
          ["Listed on NSE", idn.listed_on ?? "n/a"],
        ].map(([k, v]) => (
          <div key={k}>
            <dt className="text-ink-3">{k}</dt>
            <dd className="num text-ink-2">{v}</dd>
          </div>
        ))}
      </dl>
      {b.segments.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs text-ink-3">Revenue by segment, {b.segment_period} (segment note in the results filing)</p>
          <div className="flex h-2.5 overflow-hidden rounded-full bg-raised" aria-hidden>
            {b.segments.map((s, i) => (
              <span key={s.name} style={{ width: `${s.share * 100}%`, opacity: 1 - i * 0.18 }} className="h-full border-r border-base bg-ink-2" />
            ))}
          </div>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-ink-3">
                <th className="py-1 text-left font-normal">Segment</th>
                <th className="py-1 text-right font-normal">Revenue</th>
                <th className="py-1 text-right font-normal">Share</th>
                <th className="py-1 text-right font-normal">YoY</th>
              </tr>
            </thead>
            <tbody>
              {b.segments.map((s) => (
                <tr key={s.name} className="border-t border-line">
                  <td className="py-1.5 text-ink-2">{s.name}</td>
                  <td className="py-1.5 text-right"><Fv id={s.fact} /></td>
                  <td className="num py-1.5 text-right text-ink-2">{(s.share * 100).toFixed(0)}%</td>
                  <td className="py-1.5 text-right"><Fv id={s.growth_fact} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Gaps gaps={b.gaps} />
    </div>
  );
}

// ------------------------------------------------------------------ 2. Financial snapshot

export function Snapshot({ r }: { r: Report }) {
  const s = r.sections.snapshot;
  if (!s.period) return <Gaps gaps={s.gaps} />;
  return (
    <div className="space-y-4">
      <p className="text-xs text-ink-3">
        {s.period}, {s.basis} figures from the results filing. Changes and margins computed by FINN.
      </p>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-xs text-ink-3">
            <th className="py-1.5 text-left font-normal" />
            <th className="py-1.5 text-right font-normal">{s.period}</th>
            <th className="py-1.5 text-right font-normal">QoQ</th>
            <th className="py-1.5 text-right font-normal">YoY</th>
          </tr>
        </thead>
        <tbody>
          {s.rows.map((row) => (
            <tr key={row.key} className="border-t border-line">
              <th className="py-2 text-left font-normal text-ink-2"><ClassTag kind="reported">{row.label}</ClassTag></th>
              <td className="py-2 text-right"><Fv id={row.value} /></td>
              <td className="py-2 text-right text-xs"><Fv id={row.qoq} /></td>
              <td className="py-2 text-right text-xs"><Fv id={row.yoy} /></td>
            </tr>
          ))}
        </tbody>
      </table>
      <dl className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4">
        {[...(s.margins ?? []).map((m) => ({ label: m.label, id: m.value, sub: m.yoy_change })), ...(s.ttm ?? []).map((m) => ({ label: m.label, id: m.value, sub: null })),
          ...(s.balance ?? []).map((m) => ({ label: m.label, id: m.value, sub: null })), ...(s.market ?? []).map((m) => ({ label: m.label, id: m.value, sub: null }))]
          .filter((x) => x.id)
          .map((x) => (
            <div key={x.label}>
              <dt className="text-2xs text-ink-3">{x.label}</dt>
              <dd className="text-sm">
                <Fv id={x.id} />
                {x.sub && <span className="ml-1.5 text-2xs"><Fv id={x.sub} /></span>}
              </dd>
            </div>
          ))}
      </dl>
      {(s.market ?? []).length > 0 && <p className="text-2xs text-ink-3">Market capitalisation is exchange data (BSE scrip list), not a company document.</p>}
    </div>
  );
}

// ------------------------------------------------------------------ 3. Financial trajectory

export function Trajectory({ r }: { r: Report }) {
  const t = r.sections.trajectory;
  const fin = r.identity.is_financial;
  if (!t.quarters.length) return <Gaps gaps={t.gaps} />;
  const series = fin
    ? [
        { label: "Revenue from operations (₹ cr)", ids: t.series.revenue, kind: "bars" as const, unit: "cr" as const },
        { label: "Net interest income (₹ cr)", ids: t.series.nii ?? [], kind: "bars" as const, unit: "cr" as const },
        { label: "Profit after tax (₹ cr)", ids: t.series.pat, kind: "bars" as const, unit: "cr" as const },
      ]
    : [
        { label: "Revenue (₹ cr)", ids: t.series.revenue, kind: "bars" as const, unit: "cr" as const },
        { label: "EBITDA margin", ids: t.series.ebitda_margin ?? [], kind: "line" as const, unit: "pct" as const },
        { label: "Profit after tax (₹ cr)", ids: t.series.pat, kind: "bars" as const, unit: "cr" as const },
      ];
  return (
    <div className="space-y-5">
      <QuarterCharts quarters={t.quarters} series={series} />
      <div className="overflow-x-auto">
        <table className="w-full min-w-[440px] text-xs">
          <thead>
            <tr className="text-ink-3">
              <th className="py-1 text-left font-normal">Year on year</th>
              {t.quarters.map((q) => (
                <th key={q} className="num py-1 text-right font-normal">{q.replace(" FY", "’")}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {[["Revenue", t.series.revenue_yoy], ["PAT", t.series.pat_yoy]].map(([label, ids]) => (
              <tr key={label as string} className="border-t border-line">
                <th className="py-1.5 text-left font-normal text-ink-2">{label as string}</th>
                {(ids as (string | null)[]).map((id, i) => (
                  <td key={i} className="py-1.5 text-right"><Fv id={id} empty="" /></td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {t.annual.length > 0 && (
        <table className="w-full text-xs">
          <thead>
            <tr className="text-ink-3">
              <th className="py-1 text-left font-normal">Full year</th>
              <th className="py-1 text-right font-normal">Revenue</th>
              <th className="py-1 text-right font-normal">Growth</th>
              {!fin && <th className="py-1 text-right font-normal">EBITDA margin</th>}
              <th className="py-1 text-right font-normal">PAT</th>
            </tr>
          </thead>
          <tbody>
            {t.annual.map((a) => (
              <tr key={a.period} className="border-t border-line">
                <td className="num py-1.5 text-ink-2">{a.period}</td>
                <td className="py-1.5 text-right"><Fv id={a.revenue} /></td>
                <td className="py-1.5 text-right"><Fv id={a.revenue_growth} empty="" /></td>
                {!fin && <td className="py-1.5 text-right"><Fv id={a.ebitda_margin} /></td>}
                <td className="py-1.5 text-right"><Fv id={a.pat} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {t.restated.length > 0 && (
        <p className="text-xs text-alert">
          {t.restated.length} figure{t.restated.length > 1 ? "s were" : " was"} restated in a later filing; the later figure is used.
        </p>
      )}
      <Gaps gaps={t.gaps} />
    </div>
  );
}

// ------------------------------------------------------------------ 4 & 5. Balance sheet, cash quality

function PeriodTable({ cols, rows }: { cols: string[]; rows: { label: string; values: (string | null)[] }[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[420px] text-xs">
        <thead>
          <tr className="text-ink-3">
            <th className="py-1.5 text-left font-normal" />
            {cols.map((c) => (
              <th key={c} className="num py-1.5 text-right font-normal">{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.label} className="border-t border-line">
              <th className="py-2 pr-3 text-left font-normal text-ink-2">{row.label}</th>
              {row.values.map((id, i) => (
                <td key={i} className="py-2 text-right"><Fv id={id} empty="" /></td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function BalanceSheet({ r }: { r: Report }) {
  const b = r.sections.balance_sheet;
  if (!b.dates.length) return <Gaps gaps={b.gaps} />;
  return (
    <div className="space-y-3">
      <p className="text-xs text-ink-3">
        As at each date, from the statement of assets and liabilities filed with half-year and annual results ({b.basis}). H1 means 30 September; FY means 31 March.
      </p>
      <PeriodTable cols={b.dates} rows={b.rows} />
      {b.checks && b.checks.length > 0 && (
        <p className="text-2xs text-ink-3">
          {b.checks.every((c) => c.ok) ? "Total assets equal total equity and liabilities on every date read." : `Check failed: ${b.checks.filter((c) => !c.ok).map((c) => c.check).join("; ")}`}
        </p>
      )}
    </div>
  );
}

export function CashQuality({ r }: { r: Report }) {
  const c = r.sections.cash_quality;
  if (!c.periods.length) return <Gaps gaps={c.gaps} />;
  return (
    <div className="space-y-3">
      <PeriodTable cols={c.periods} rows={c.rows} />
      {c.flags.length > 0 && (
        <ul className="space-y-1.5">
          {c.flags.map((f, i) => (
            <li key={i} className="flex items-start gap-2 text-sm">
              <span className={`mt-0.5 text-2xs font-medium ${f.tone === "bull" ? "text-up" : "text-down"}`}>{f.tone === "bull" ? "Strength" : "Watch"}</span>
              <span className="text-ink-2">{f.text}</span>
            </li>
          ))}
        </ul>
      )}
      {c.note && <p className="text-xs text-ink-3">{c.note}</p>}
    </div>
  );
}

// ------------------------------------------------------------------ 7. Management guidance

export function Guidance({ r }: { r: Report }) {
  const statements = r.claims.filter((c) => c.kind === "guidance");
  const explicit = statements.filter((c) => c.explicit);
  const qualitative = statements.filter((c) => !c.explicit);
  const verdictOf = (c: RClaim) =>
    r.ledger.find((e) => e.kind === "guidance" && e.history.some((h) => h.claim_id === c.id)) ?? null;
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <SectionHead title="Explicit guidance" count={explicit.length} />
        <p className="text-xs text-ink-3">A number and a period, in management&apos;s own words. The target shown is parsed from the quote by code, never inferred.</p>
        <StatementList items={explicit} verdictOf={verdictOf} />
      </div>
      <div className="space-y-2">
        <SectionHead title="Qualitative guidance" count={qualitative.length} />
        <p className="text-xs text-ink-3">A direction or worded quantity for a metric and period, with no number. Withdrawals of guidance appear here too.</p>
        <StatementList items={qualitative} verdictOf={verdictOf} />
      </div>
      <div className="space-y-3">
        <SectionHead title="Commentary by theme" count={r.sections.guidance.commentary.reduce((a, c) => a + c.facts.length, 0)} />
        <p className="text-xs text-ink-3">Management&apos;s descriptive statements, not targets. Tone is a word-list reading by FINN.</p>
        {r.sections.guidance.commentary.length === 0 && <p className="text-sm text-ink-2">None found.</p>}
        {r.sections.guidance.commentary.map((t) => (
          <Theme key={t.theme} theme={t.theme} ids={t.facts} claims={r.claims} />
        ))}
      </div>
    </div>
  );
}

function StatementList({ items, verdictOf }: { items: RClaim[]; verdictOf: (c: RClaim) => Report["ledger"][number] | null }) {
  if (!items.length) return <p className="text-sm text-ink-2">None in the documents read.</p>;
  return (
    <ul className="divide-y divide-line border-y border-line">
      {items.map((c) => {
        const e = verdictOf(c);
        return (
          <li key={c.id} className="grid gap-2 py-3 sm:grid-cols-[minmax(0,1fr)_auto]">
            <div className="space-y-1.5">
              <p className="flex flex-wrap items-baseline gap-x-2 text-xs">
                <span className="font-medium text-ink">{c.metric_label ?? "Guidance"}{c.segment ? ` (${c.segment})` : ""}</span>
                {c.period && <span className="num text-ink-3">{c.period}</span>}
                {c.withdraws ? <span className="text-down">Withdrawn</span> : c.target && <ClassTag kind="guidance"><span>{c.target.kind === "words" ? `“${c.target.text}”` : c.target.kind === "direction" ? "direction only" : c.target.text}</span></ClassTag>}
                {c.hedge && <span className="text-ink-3">{c.hedge}</span>}
              </p>
              <Said id={c.fact_id} compact />
              {c.target && <p className="text-2xs text-ink-3">{c.target.reading}</p>}
            </div>
            {e && <div className="sm:text-right"><Verdict v={e.verdict} note={e.status_note} /></div>}
          </li>
        );
      })}
    </ul>
  );
}

function Theme({ theme, ids, claims }: { theme: string; ids: string[]; claims: RClaim[] }) {
  const [open, setOpen] = useState(false);
  const tones = ids.map((id) => claims.find((c) => c.fact_id === id)?.tone ?? "neutral");
  const pos = tones.filter((t) => t === "positive").length;
  const neg = tones.filter((t) => t === "negative").length;
  return (
    <div className="border-b border-line pb-2">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} className="flex w-full items-center gap-2 py-1 text-left">
        <Chevron open={open} />
        <span className="flex-1 text-sm text-ink">{theme}</span>
        <span className="num text-2xs text-ink-3">
          {ids.length} statement{ids.length > 1 ? "s" : ""}
          {pos ? <span className="text-up">, {pos} upbeat</span> : null}
          {neg ? <span className="text-down">, {neg} cautious</span> : null}
        </span>
      </button>
      {open && (
        <ul className="ml-5 mt-2 space-y-3">
          {ids.map((id) => (
            <li key={id}>
              <Said id={id} compact />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ 8. Bull vs Bear

export function BullBear({ r }: { r: Report }) {
  const b = r.sections.bull_bear;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-6 md:grid-cols-2 [&>*]:min-w-0">
        {([["Bull case", b.bull, "text-up"], ["Bear case", b.bear, "text-down"]] as const).map(([title, pts, cls]) => (
          <div key={title} className="space-y-3">
            <h3 className={`text-sm font-semibold ${cls}`}>{title}</h3>
            {pts.length === 0 ? (
              <p className="text-sm text-ink-3">No rule fired on this side for the evidence read.</p>
            ) : (
              <ul className="space-y-3">
                {pts.map((p) => (
                  <li key={p.id} className="space-y-1.5">
                    <p className="text-sm text-ink">{p.text}</p>
                    <Cites ids={p.evidence} />
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </div>
      <p className="flex items-start gap-2 text-xs text-ink-3">
        <ClassTag kind="computed"><span className="sr-only">FINN rule</span></ClassTag>
        {b.note}
      </p>
    </div>
  );
}

// ------------------------------------------------------------------ Sources

const SRC: Record<string, string> = { bse: "BSE", nse: "NSE", company_ir: "Company IR", fixture: "Fixture" };

export function Sources({ r }: { r: Report }) {
  const failed = r.fetch_log.filter((l) => !l.ok);
  return (
    <div className="space-y-5">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-xs">
          <thead>
            <tr className="text-ink-3">
              <th className="py-1.5 text-left font-normal">Document</th>
              <th className="py-1.5 text-left font-normal">Period</th>
              <th className="py-1.5 text-left font-normal">Source</th>
              <th className="py-1.5 text-left font-normal">Filed</th>
              <th className="py-1.5 text-left font-normal">Read</th>
            </tr>
          </thead>
          <tbody>
            {[...r.documents].sort((a, b) => (b.filed_at ?? "").localeCompare(a.filed_at ?? "")).map((d) => (
              <tr key={d.id} className="border-t border-line align-top">
                <td className="max-w-[18rem] py-2 pr-3">
                  <p className="text-ink-2">{DOC_KIND[d.kind]}</p>
                  <p className="truncate text-2xs text-ink-3" title={d.title}>{d.title}</p>
                </td>
                <td className="num py-2 pr-3 text-ink-2">
                  {d.period}
                  <p className="text-2xs text-ink-3">{d.period_basis}</p>
                </td>
                <td className="py-2 pr-3 text-ink-2">
                  {SRC[d.source] ?? d.source}
                  {d.source_id && <p className="num text-2xs text-ink-3">{d.source_id}</p>}
                  {!d.fixture && safeUrl(d.url) && <a href={safeUrl(d.url)!} target="_blank" rel="noreferrer" className="text-2xs text-brass hover:underline">Open ↗</a>}
                </td>
                <td className="num py-2 pr-3 text-ink-2">{d.filed_at ? `${dayIST(d.filed_at)} ${new Date(d.filed_at).getFullYear()}` : "n/a"}</td>
                <td className="py-2">
                  <span className={d.status === "parsed" ? (d.status_reason ? "text-alert" : "text-ink-2") : "text-down"}>
                    {d.status === "parsed" ? `${d.pages ?? "?"} pages` : d.status}
                  </span>
                  <p className="text-2xs text-ink-3">
                    {[
                      d.status_reason,
                      d.parse.downloaded_from ? `from the ${d.parse.downloaded_from}` : null,
                      d.parse.statements?.length ? d.parse.statements.join(", ") : null,
                      d.parse.unit ? `in ${d.parse.unit}` : null,
                      d.kind === "transcript" && d.parse.turns ? `${d.parse.management_turns} management and ${d.parse.analyst_turns} analyst turns` : null,
                      d.parse.claims ? `${(d.parse.claims.guidance ?? 0) + (d.parse.claims.assertion ?? 0) + (d.parse.claims.outlook ?? 0)} statements` : null,
                    ].filter(Boolean).join("; ")}
                  </p>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {r.rejections.length > 0 && (
        <div className="space-y-1">
          <p className="text-xs font-medium text-ink-2">Filings rejected</p>
          {r.rejections.map((x) => (
            <p key={x} className="text-xs text-ink-3">{x}</p>
          ))}
        </div>
      )}
      {failed.length > 0 && (
        <div className="space-y-1">
          <p className="text-xs font-medium text-ink-2">Fetches that failed ({failed.length} of {r.fetch_log.length})</p>
          {failed.map((l, i) => (
            <p key={i} className="text-xs text-ink-3">
              {l.source.toUpperCase()} {l.target}: {l.error}
            </p>
          ))}
        </div>
      )}
      <p className="text-2xs text-ink-3">
        Evidence audit: {r.audit.reported} reported figures with page and row, {r.audit.quotes} quotes found on their page, {r.audit.computed} computed figures with formula and inputs,
        {" "}{r.audit.points} findings with cited evidence. {r.counts.claims_rejected_by_gates} statements were rejected by the quote and number checks. Versions:{" "}
        {Object.entries(r.versions).map(([k, v]) => `${k} ${v}`).join(", ")}.
      </p>
    </div>
  );
}

export function docTitle(id?: string | null) {
  const d = docOf(id);
  return d ? `${DOC_KIND[d.kind]}${d.period ? ` ${d.period}` : ""}` : "";
}

export function factLabel(id?: string | null) {
  return factOf(id)?.label ?? "";
}
