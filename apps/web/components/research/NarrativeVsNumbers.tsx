"use client";

import { useState } from "react";
import { docOf, factOf, type Report, type RLedger } from "@/lib/research";
import { useStore } from "@/lib/store";
import { Chevron, ClassTag, SectionHead } from "../ui/primitives";
import { Cites, Fv, Said, Verdict } from "./report-ui";

export const CHANGE: Record<string, { label: string; cls: string }> = {
  first: { label: "First stated", cls: "text-ink-2" },
  "also stated": { label: "Also stated", cls: "text-ink-3" },
  differs: { label: "Different figure in another document", cls: "text-down" },
  reiterated: { label: "Reiterated", cls: "text-ink-2" },
  raised: { label: "Raised", cls: "text-up" },
  lowered: { label: "Lowered", cls: "text-down" },
  changed: { label: "Changed", cls: "text-alert" },
  softened: { label: "Restated in words only", cls: "text-alert" },
  "not repeated": { label: "Not repeated", cls: "text-alert" },
  withdrawn: { label: "Withdrawn", cls: "text-down" },
};

const HEDGE: Record<string, string> = {
  firm: "Firm wording",
  expected: "“Expect” wording",
  aspirational: "Aspirational wording",
  conditional: "Conditional wording",
};

/** Headline counts for the top of the company page. */
export function NvnSummary({ r }: { r: Report }) {
  const g = r.ledger.filter((e) => e.kind === "guidance");
  const explicit = g.filter((e) => e.explicit);
  const count = (pred: (e: RLedger) => boolean) => explicit.filter(pred).length;
  const kept = count((e) => e.verdict === "delivered" || e.verdict === "ahead");
  const missed = count((e) => e.verdict === "missed");
  const risk = count((e) => (e.verdict === "pending" && e.status_note === "at risk") || /behind/.test(e.status_note ?? ""));
  const dropped = count((e) => e.verdict === "dropped");
  const open = count((e) => e.verdict === "pending");
  const top = r.sections.nvn.discrepancies.filter((d) => d.severity >= 2).slice(0, 3);
  const calls = r.sections.nvn.calls;
  if (!g.length && !top.length) return null;
  return (
    <section aria-labelledby="nvn-summary" className="space-y-3 rounded-lg border border-line-strong bg-surface p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="nvn-summary" className="text-sm font-semibold">Narrative vs Numbers</h2>
        <a href="#nvn" className="inline-flex min-h-6 items-center text-xs text-brass hover:underline">Full ledger ›</a>
      </div>
      <dl className="grid grid-cols-3 gap-3 sm:grid-cols-6">
        {[
          ["Explicit targets", explicit.length, ""],
          ["Kept", kept, "text-up"],
          ["Missed", missed, missed ? "text-down" : ""],
          ["Dropped", dropped, dropped ? "text-alert" : ""],
          ["Behind / at risk", risk, risk ? "text-alert" : ""],
          ["Still open", open, ""],
        ].map(([label, v, cls]) => (
          <div key={label as string}>
            <dt className="text-2xs text-ink-3">{label}</dt>
            <dd className={`num text-lg font-medium ${cls}`}>{v}</dd>
          </div>
        ))}
      </dl>
      {top.length > 0 && (
        <ul className="space-y-1.5 border-t border-line pt-3">
          {top.map((d) => (
            <li key={d.id} className="flex gap-2 text-sm text-ink-2">
              <ClassTag kind="computed"><span className="sr-only">FINN check</span></ClassTag>
              <span>{d.text}</span>
            </li>
          ))}
        </ul>
      )}
      <p className="text-2xs text-ink-3">
        From {calls.length} call transcript{calls.length === 1 ? "" : "s"}
        {r.counts.documents.presentation ? `, ${r.counts.documents.presentation} presentation${r.counts.documents.presentation > 1 ? "s" : ""}` : ""}
        {r.counts.documents.annual_report ? " and the annual report" : ""}, compared with {r.counts.documents.results} results filing{r.counts.documents.results === 1 ? "" : "s"}.
      </p>
    </section>
  );
}

export function NarrativeVsNumbers({ r }: { r: Report }) {
  const byId = Object.fromEntries(r.ledger.map((e) => [e.id, e]));
  const entries = r.sections.nvn.entries.map((id) => byId[id]).filter(Boolean);
  const guidance = entries.filter((e) => e.kind === "guidance");
  const explicit = guidance.filter((e) => e.explicit);
  const qualitative = guidance.filter((e) => !e.explicit);
  const assertions = entries.filter((e) => e.kind === "assertion");
  const disc = r.sections.nvn.discrepancies;
  const shifts = r.sections.nvn.shifts;
  const noTranscripts = r.sections.nvn.calls.length === 0;

  return (
    <div className="space-y-8">
      {noTranscripts && (
        <p className="rounded-md border border-line bg-surface p-3 text-sm text-ink-2">
          No earnings-call transcript was found for the quarters read, so there is little management narrative to test. Anything below comes from presentations or the annual report.
        </p>
      )}

      <div className="space-y-3">
        <SectionHead title="Where the story and the numbers part ways" count={disc.length} />
        {disc.length === 0 ? (
          <p className="text-sm text-ink-2">No discrepancy rule fired on the documents read. That isn&apos;t a clean bill: it means nothing reached a threshold FINN tests for.</p>
        ) : (
          <ol className="space-y-4">
            {disc.map((d) => (
              <li key={d.id} className="space-y-1.5 border-l-2 pl-3" style={{ borderColor: d.severity >= 3 ? "var(--color-down)" : d.severity >= 2 ? "var(--color-alert)" : "var(--color-line-strong)" }}>
                <p className="text-sm text-ink">{d.text}</p>
                {d.implication && (
                  <p className="text-sm text-ink-2">
                    <span className="text-2xs font-medium uppercase tracking-[0.06em] text-ink-3">Implication </span>
                    {d.implication}
                  </p>
                )}
                <Cites ids={d.evidence} />
              </li>
            ))}
          </ol>
        )}
      </div>

      <div className="space-y-3">
        <SectionHead title="Explicit guidance against results" count={explicit.length} />
        <p className="text-xs text-ink-3">
          Targets management stated as numbers. FINN checks each against reported figures in code; open periods show the year-to-date run-rate and what the rest of the
          period needs.
        </p>
        {explicit.length === 0 ? <p className="text-sm text-ink-2">Management stated no numeric targets in the documents read.</p> : <LedgerTable rows={explicit} />}
      </div>

      {qualitative.length > 0 && (
        <div className="space-y-3">
          <SectionHead title="Qualitative statements about a metric" count={qualitative.length} />
          <p className="text-xs text-ink-3">
            Directional or worded statements (“margins to improve”, “high single digits”). Directions are checked for sign only; worded quantities aren&apos;t scored, and the
            actual is shown for context.
          </p>
          <LedgerTable rows={qualitative} />
        </div>
      )}

      <div className="space-y-3">
        <SectionHead title="What management said about the quarters reported" count={assertions.length} />
        <p className="text-xs text-ink-3">Figures management quoted on calls and in presentations, checked against the statements on every plausible basis before being called inconsistent.</p>
        {assertions.length === 0 ? <p className="text-sm text-ink-2">No checkable statements about reported periods.</p> : <AssertionList rows={assertions} />}
      </div>

      <div className="space-y-3">
        <SectionHead title="Changes in management narrative" count={shifts.length} />
        {shifts.length === 0 ? (
          <p className="text-sm text-ink-2">Management&apos;s tone on the themes FINN tracks didn&apos;t turn between the calls read.</p>
        ) : (
          <ul className="space-y-4">
            {shifts.map((s) => (
              <li key={s.id} className="space-y-2">
                <p className="text-sm text-ink">
                  <span className="font-medium">{s.theme}</span>
                  <span className="text-ink-3">: </span>
                  <span className={s.from_tone === "positive" ? "text-up" : s.from_tone === "negative" ? "text-down" : "text-ink-3"}>{s.from_tone}</span>
                  {s.from_call ? ` (${s.from_call})` : ""} <span className="text-ink-3">→</span>{" "}
                  <span className={s.to_tone === "negative" ? "text-down" : "text-up"}>{s.to_tone}</span> ({s.to_call})
                </p>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 [&>*]:min-w-0">
                  {s.evidence.map((id) => (
                    <div key={id} className="rounded-md border border-line bg-base p-3">
                      <Said id={id} compact />
                    </div>
                  ))}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <Coverage r={r} />
    </div>
  );
}

function LedgerTable({ rows }: { rows: RLedger[] }) {
  return (
    <ul className="divide-y divide-line border-y border-line">
      {rows.map((e) => (
        <LedgerRow key={e.id} e={e} />
      ))}
    </ul>
  );
}

function LedgerRow({ e }: { e: RLedger }) {
  const [open, setOpen] = useState(e.severity >= 2);
  const { openEvidence } = useStore();
  const latestQuote = [...e.history].reverse().find((h) => h.fact_id)?.fact_id;
  return (
    <li className="py-3">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} className="flex w-full flex-wrap items-start gap-x-3 gap-y-1.5 text-left sm:flex-nowrap">
        <span className="mt-1 text-ink-3"><Chevron open={open} /></span>
        <span className="min-w-0 flex-1 basis-[calc(100%-2rem)] space-y-1 sm:basis-auto">
          <span className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
            <span className="text-sm font-medium text-ink">{e.metric_label}</span>
            <span className="num text-xs text-ink-3">{e.period}</span>
            {e.target && (
              <span className="inline-flex items-center gap-1 text-sm text-guided">
                <ClassTag kind="guidance"><span className="num">{e.target}</span></ClassTag>
              </span>
            )}
          </span>
          <span className="block text-xs text-ink-2">{e.detail}</span>
        </span>
        <span className="ml-6 shrink-0 sm:ml-0"><Verdict v={e.verdict} note={e.status_note} /></span>
      </button>
      {open && (
        <div className="ml-6 mt-3 space-y-3">
          {latestQuote && <Said id={latestQuote} />}
          <dl className="grid gap-x-6 gap-y-1 text-xs sm:grid-cols-2">
            {e.reading && (
              <div className="sm:col-span-2">
                <dt className="inline text-ink-3">How FINN read it: </dt>
                <dd className="inline text-ink-2">{e.reading}</dd>
              </div>
            )}
            {e.hedge && (
              <div>
                <dt className="inline text-ink-3">Wording: </dt>
                <dd className="inline text-ink-2">{HEDGE[e.hedge] ?? e.hedge}</dd>
              </div>
            )}
            {e.actual_fact && (
              <div>
                <dt className="inline text-ink-3">Actual: </dt>
                <dd className="inline"><Fv id={e.actual_fact} /></dd>
              </div>
            )}
            {e.required_fact && (
              <div>
                <dt className="inline text-ink-3">{factOf(e.required_fact)?.label.startsWith("Gap") ? "Gap: " : "Rest of period needs: "}</dt>
                <dd className="inline"><Fv id={e.required_fact} /></dd>
              </div>
            )}
          </dl>
          <ol className="space-y-1.5" aria-label="History">
            {e.history.map((h, i) => {
              const c = CHANGE[h.change];
              const d = docOf(h.doc_id);
              return (
                <li key={i} className="flex flex-wrap items-baseline gap-x-2 text-xs">
                  <span className="num w-16 shrink-0 text-ink-3">{h.call ?? "?"}</span>
                  <span className={`font-medium ${c.cls}`}>{c.label}</span>
                  {h.target && <span className="num text-guided">{h.target}</span>}
                  {d && <span className="text-ink-3">{d.kind === "transcript" ? "call" : d.kind.replace("_", " ")}</span>}
                  {h.fact_id && (
                    <button type="button" onClick={() => openEvidence(h.fact_id!)} className="inline-flex min-h-6 items-center text-2xs text-brass hover:underline">
                      quote, p.{factOf(h.fact_id)?.page}
                    </button>
                  )}
                </li>
              );
            })}
          </ol>
        </div>
      )}
    </li>
  );
}

function AssertionList({ rows }: { rows: RLedger[] }) {
  return (
    <ul className="divide-y divide-line border-y border-line">
      {rows.map((e) => (
        <li key={e.id} className="grid grid-cols-1 gap-2 py-3 sm:grid-cols-[minmax(0,1fr)_auto] [&>*]:min-w-0">
          <div className="space-y-1.5">
            <Said id={e.evidence[0]} compact />
            <p className="text-xs text-ink-2">{e.detail}</p>
          </div>
          <div className="sm:text-right"><Verdict v={e.verdict} /></div>
        </li>
      ))}
    </ul>
  );
}

function Coverage({ r }: { r: Report }) {
  const calls = r.sections.nvn.calls;
  const results = r.documents.filter((d) => d.kind === "results" && d.status === "parsed").map((d) => d.period);
  const key = (q: string) => {
    const m = /^Q(\d) FY(\d{2})$/.exec(q);
    return m ? Number(m[2]) * 10 + Number(m[1]) : 0;
  };
  const quarters = (Array.from(new Set([...results, ...calls.map((c) => c.period)])).filter(Boolean) as string[]).sort((a, b) => key(a) - key(b));
  if (!quarters.length) return null;
  return (
    <div className="space-y-2">
      <SectionHead title="Coverage" />
      <table className="text-xs">
        <thead>
          <tr className="text-ink-3">
            <th className="py-1 pr-6 text-left font-normal">Quarter</th>
            <th className="py-1 pr-6 text-left font-normal">Results</th>
            <th className="py-1 text-left font-normal">Call transcript</th>
          </tr>
        </thead>
        <tbody>
          {quarters.map((q) => {
            const c = calls.find((x) => x.period === q);
            return (
              <tr key={q} className="border-t border-line">
                <td className="num py-1.5 pr-6 text-ink-2">{q}</td>
                <td className="py-1.5 pr-6">{results.includes(q) ? <span className="text-ink-2">Read</span> : <span className="text-alert">Missing</span>}</td>
                <td className="py-1.5">{c ? c.complete ? <span className="text-ink-2">Read, speakers identified</span> : <span className="text-alert">Read, no speaker labels</span> : <span className="text-alert">Not found</span>}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
