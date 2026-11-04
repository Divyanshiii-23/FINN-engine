"use client";

import Link from "next/link";
import { useState } from "react";
import { factOf, useReport, type CredIndicator, type CredRow, type Credibility, type Report } from "@/lib/research";
import { useStore } from "@/lib/store";
import { Chevron, ClassMark, ClassTag, SectionHead } from "../ui/primitives";
import { CHANGE } from "./NarrativeVsNumbers";
import { Cites, Fv, Said, Verdict } from "./report-ui";
import { LaneChart } from "./CredibilityLane";

const STATUS: Record<CredIndicator["status"], { label: (n: number) => string; cls: string }> = {
  observed: { label: (n) => `${n} observation${n === 1 ? "" : "s"}`, cls: "text-ink-2 border-line-strong" },
  insufficient: { label: (n) => `Not enough history (n = ${n})`, cls: "text-alert border-alert/45" },
  none: { label: () => "Nothing to assess", cls: "text-ink-3 border-line" },
};

export function CredibilityScreen({ symbol }: { symbol: string }) {
  const { state } = useReport(symbol);
  if (state.status === "loading") return <div className="h-40" aria-busy="true" aria-label="Loading" />;
  if (state.status !== "ready" || !state.report.credibility)
    return (
      <div className="space-y-3">
        <Link href={`/research/${symbol}`} className="text-xs text-ink-3 hover:text-ink-2">‹ {symbol}</Link>
        <p className="text-sm text-ink-2">No credibility history for {symbol} yet. Build the research report first.</p>
      </div>
    );
  return <Body r={state.report} c={state.report.credibility} />;
}

/** The four kinds of information on this page, and how each is drawn. */
function Legend() {
  return (
    <ul className="flex flex-wrap gap-x-5 gap-y-1.5 text-2xs text-ink-2" aria-label="Legend">
      <li className="inline-flex items-center gap-1.5"><ClassMark kind="guidance" className="text-guided" />Explicit guidance: a number and a period</li>
      <li className="inline-flex items-center gap-1.5"><ClassMark kind="outlook" className="text-guided" />Qualitative statement: direction or words, not scored</li>
      <li className="inline-flex items-center gap-1.5"><ClassMark kind="reported" className="text-ink-2" />Reported outcome, from the filed statements</li>
      <li className="inline-flex items-center gap-1.5"><ClassMark kind="generated" className="text-ai" />FINN interpretation</li>
    </ul>
  );
}

function Body({ r, c }: { r: Report; c: Credibility }) {
  const idn = r.identity;
  const w = c.window;
  const ind = Object.fromEntries(c.indicators.map((i) => [i.id, i]));
  const order = ["delivery", "landing", "revisions", "capex", "revenue", "margins", "cash", "silence", "quoted"];
  return (
    <div className="space-y-8">
      <header className="space-y-3">
        <Link href={`/research/${idn.symbol}`} className="text-xs text-ink-3 hover:text-ink-2">‹ {idn.symbol} research</Link>
        <div>
          <h1 className="text-xl font-semibold tracking-[0.01em]">Management credibility</h1>
          <p className="text-sm text-ink-2">
            {idn.name}. What management said, set against what was later reported.
          </p>
        </div>
        <p className="text-xs text-ink-3">
          {w.calls} call transcripts ({w.first_call}–{w.last_call}) and {w.results} results filings; periods closed: {w.closed_years.length ? w.closed_years.join(", ") : "none yet"}.
        </p>
        {r.dataset === "fixture" && (
          <p role="note" className="rounded-md border border-alert/40 bg-alert/5 px-3 py-2 text-xs text-alert">
            Synthetic test company: every statement and figure here comes from fictional documents generated to test the pipeline.
          </p>
        )}
        <p className="max-w-[72ch] text-xs leading-relaxed text-ink-2">
          No trust score: combining these indicators would need weights, and any weighting is a judgement, not a measurement. A rate is shown only from {c.rules.min_closed} closed explicit targets across {c.rules.min_years} fiscal years; below that, the observations are listed without one.
        </p>
        <Legend />
      </header>

      <Interpretation c={c} />

      {c.contradictions.length > 0 && (
        <section aria-labelledby="contra" className="space-y-3">
          <SectionHead id="contra" title="Where commentary and statements disagree" count={c.contradictions.length} />
          <ul className="space-y-4">
            {c.contradictions.map((p) => (
              <li key={p.id} className="space-y-1.5 border-l-2 border-down/60 pl-3">
                <p className="text-sm text-ink">{p.text}</p>
                {p.implication && <p className="text-xs text-ink-2">{p.implication}</p>}
                <Cites ids={p.evidence} />
              </li>
            ))}
          </ul>
        </section>
      )}

      <section aria-labelledby="track" className="space-y-4">
        <SectionHead id="track" title="Track record" />
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 [&>*]:min-w-0">
          {order.filter((k) => ind[k]).map((k) => (
            <IndicatorCard key={k} i={ind[k]} />
          ))}
        </div>
      </section>

      <section aria-labelledby="timeline" className="space-y-5">
        <SectionHead id="timeline" title="Statements against outcomes, over time" count={c.lanes.length} />
        {c.lanes.length === 0 && <p className="text-sm text-ink-2">Management gave no guidance about a metric in the documents read.</p>}
        {c.lanes.map((l) => (
          <div key={l.id} className="rounded-lg border border-line p-3 sm:p-4">
            <LaneChart lane={l} />
          </div>
        ))}
      </section>
    </div>
  );
}

function Interpretation({ c }: { c: Credibility }) {
  if (!c.interpretation.length) return null;
  const model = c.interpretation.some((p) => p.method !== "rules");
  return (
    <section aria-labelledby="interp" className="space-y-3 rounded-lg border border-line-strong bg-surface p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="interp" className="text-sm font-semibold"><ClassTag kind="generated">FINN interpretation</ClassTag></h2>
        <p className="text-2xs text-ink-3">{model ? "Reworded by a model; every number checked against the cited facts" : "Written by fixed rules from the cited facts; no model"}</p>
      </div>
      <ul className="space-y-3">
        {c.interpretation.map((p) => (
          <li key={p.id} className="space-y-1.5">
            <p className="font-serif text-[15px] leading-relaxed text-ink">{p.text}</p>
            <Cites ids={p.evidence.slice(0, 6)} />
          </li>
        ))}
      </ul>
    </section>
  );
}

function IndicatorCard({ i }: { i: CredIndicator }) {
  const [open, setOpen] = useState(false);
  const st = STATUS[i.status];
  const hasRows = i.rows.length > 0 || (i.management_said?.length ?? 0) > 0;
  return (
    <article className="space-y-2 rounded-lg border border-line p-4" aria-labelledby={`ind-${i.id}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h3 id={`ind-${i.id}`} className="text-sm font-medium text-ink">{i.title}</h3>
        <span className={`inline-flex h-5 items-center rounded-sm border px-1.5 text-2xs ${st.cls}`}>{st.label(i.n)}</span>
      </div>
      <p className="text-2xs text-ink-3">{i.question}</p>
      <p className="text-sm text-ink-2">{i.headline}</p>
      {i.id === "delivery" && i.by_family && i.by_family.length > 0 && (
        <ul className="flex flex-wrap gap-1.5">
          {i.by_family.map((f) => (
            <li key={f.family} className="rounded-sm border border-line px-1.5 py-0.5 text-2xs text-ink-2">
              {f.family}: <span className="text-up">{f.kept} kept</span>{f.missed ? <span className="text-down">, {f.missed} missed</span> : null}
            </li>
          ))}
        </ul>
      )}
      {hasRows && (
        <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} className="inline-flex items-center gap-1.5 text-xs text-brass hover:underline">
          <Chevron open={open} /> {open ? "Hide" : "Show"} the observations
        </button>
      )}
      {open && <Rows i={i} />}
      {open && <p className="border-t border-line pt-2 text-2xs text-ink-3">{i.method}</p>}
    </article>
  );
}

function Rows({ i }: { i: CredIndicator }) {
  const { openEvidence } = useStore();
  if (i.id === "cash")
    return (
      <div className="space-y-3">
        {i.rows.length > 0 && (
          <table className="w-full text-xs">
            <thead>
              <tr className="text-ink-3">
                <th className="py-1 text-left font-normal">Year</th>
                <th className="py-1 text-right font-normal">OCF ÷ PAT</th>
                <th className="py-1 text-right font-normal">OCF ÷ EBITDA</th>
                <th className="py-1 text-right font-normal">Free cash flow</th>
              </tr>
            </thead>
            <tbody>
              {i.rows.map((r) => (
                <tr key={String(r.period)} className="border-t border-line">
                  <td className="num py-1.5 text-ink-2">{String(r.period)}</td>
                  <td className="py-1.5 text-right"><Fv id={r.ocf_pat as string} /></td>
                  <td className="py-1.5 text-right"><Fv id={r.ocf_ebitda as string} /></td>
                  <td className="py-1.5 text-right"><Fv id={r.fcf as string} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {(i.management_said ?? []).length > 0 && (
          <div className="space-y-2">
            <p className="text-2xs text-ink-3">What management said about cash</p>
            {(i.management_said ?? []).map((id) => <Said key={id} id={id} compact />)}
          </div>
        )}
      </div>
    );
  return (
    <ul className="divide-y divide-line border-y border-line">
      {i.rows.map((r) => (
        <li key={r.ledger} className="space-y-1.5 py-2.5">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <p className="text-xs">
              <span className="font-medium text-ink">{r.metric}</span> <span className="num text-ink-3">{r.period}</span>
            </p>
            <Verdict v={r.verdict} />
          </div>
          <p className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-xs text-ink-2">
            {r.first_target && r.first_target !== r.target ? (
              <span>Guided <span className="num text-guided">{r.first_target}</span> → <span className="num text-guided">{r.target}</span></span>
            ) : r.target ? (
              <span>Guided <span className="num text-guided">{r.target}</span></span>
            ) : null}
            {r.actual && <span>Reported <Fv id={r.actual} /></span>}
            {typeof r.offset_display === "string" && <span>vs midpoint <span className={`num ${r.side === "adverse" ? "text-down" : r.side === "favourable" ? "text-up" : "text-ink-2"}`}>{r.offset_display}</span></span>}
            {r.execution ? <span>Of first plan <Fv id={r.execution as string} /></span> : null}
            {r.first_target_met === false && <span className="text-alert">first-stated target missed</span>}
            {typeof r.kind === "string" && i.id !== "delivery" && <span className="text-ink-3">{r.kind}</span>}
          </p>
          {Array.isArray(r.changes) && (
            <p className="flex flex-wrap gap-x-3 text-2xs">
              {(r.changes as { call: string; change: string; target: string; fact: string }[]).map((ch, k) => (
                <button key={k} type="button" onClick={() => ch.fact && openEvidence(ch.fact)} className={`${CHANGE[ch.change]?.cls ?? ""} hover:underline`}>
                  {ch.call}: {CHANGE[ch.change]?.label} {ch.target}
                </button>
              ))}
            </p>
          )}
          {Array.isArray(r.quiet) && (
            <p className="text-2xs text-alert">
              {(r.quiet as { call: string; change: string }[]).map((q) => `${CHANGE[q.change]?.label ?? q.change} on ${q.call}`).join(" · ")}
            </p>
          )}
          {typeof r.note === "string" && r.verdict === "unverifiable" && <p className="text-2xs text-ink-3">{r.note}</p>}
          <FirstQuote row={r} />
        </li>
      ))}
      {i.path && i.path.length > 0 && (
        <li className="flex flex-wrap gap-x-4 gap-y-1 py-2.5 text-xs text-ink-2">
          <span className="text-ink-3">Reported by year:</span>
          {i.path.map((p) => (
            <span key={p.period}>{p.period} <Fv id={p.fact} /></span>
          ))}
        </li>
      )}
    </ul>
  );
}

function FirstQuote({ row }: { row: CredRow }) {
  const q = row.evidence.find((id) => factOf(id)?.quote);
  return q ? <Said id={q} compact /> : null;
}

/** Card on the company research page. */
export function CredibilityCard({ r }: { r: Report }) {
  const c = r.credibility;
  if (!c) return null;
  const d = c.indicators.find((i) => i.id === "delivery");
  const lead = c.interpretation.filter((p) => p.rule !== "delivery_observed").slice(0, 2);
  return (
    <section aria-labelledby="cred-card" className="space-y-2.5 rounded-lg border border-line-strong bg-surface p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="cred-card" className="text-sm font-semibold">Management credibility</h2>
        <Link href={`/research/${r.identity.symbol}/credibility`} className="text-xs text-brass hover:underline">Open the tracker ›</Link>
      </div>
      <p className="text-sm text-ink-2">{d?.headline}</p>
      {lead.map((p) => (
        <p key={p.id} className="flex gap-2 font-serif text-[14px] leading-relaxed text-ink">
          <ClassMark kind="generated" className="mt-1.5 text-ai" />
          <span>{p.text}</span>
        </p>
      ))}
      <p className="text-2xs text-ink-3">{c.window.calls} calls, {c.window.first_call}–{c.window.last_call}. No composite score.</p>
    </section>
  );
}
