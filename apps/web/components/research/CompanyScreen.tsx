"use client";

import Link from "next/link";
import { useCallback } from "react";
import { STAGES, useJob, useReport, type Job, type Report } from "@/lib/research";
import { companyOf, useFeed } from "@/lib/feed";
import { dayIST, pct, rupees, signClass, timeIST } from "@/lib/format";
import { SectionHead } from "../ui/primitives";
import { Sparkline } from "../ui/Sparkline";
import { NarrativeVsNumbers, NvnSummary } from "./NarrativeVsNumbers";
import { BalanceSheet, BullBear, Business, CashQuality, Guidance, Snapshot, Sources, Trajectory } from "./ReportSections";
import { Gaps } from "./report-ui";
import { CredibilityCard } from "./Credibility";
import { AskFinn } from "./AskFinn";

const SECTIONS: [string, string][] = [
  ["ask", "Ask FINN"],
  ["business", "1 Business"],
  ["snapshot", "2 Snapshot"],
  ["trajectory", "3 Trajectory"],
  ["balance", "4 Balance sheet"],
  ["cash", "5 Cash quality"],
  ["nvn", "6 Narrative vs Numbers"],
  ["guidance", "7 Guidance"],
  ["bullbear", "8 Bull vs Bear"],
  ["sources", "Sources"],
];

export function CompanyScreen({ symbol }: { symbol: string }) {
  const { state, reload } = useReport(symbol);
  if (state.status === "loading") return <div className="h-40" aria-busy="true" aria-label="Loading research" />;
  if (state.status === "error")
    return (
      <div className="space-y-3">
        <BackLink />
        <h1 className="text-xl font-semibold">{symbol}</h1>
        <p className="text-sm text-down">{state.message}</p>
      </div>
    );
  if (state.status === "none") return <NoReport symbol={symbol} engine={state.engine} initialJob={state.job} onDone={reload} />;
  return <ReportView r={state.report} engine={state.engine} onRefreshed={reload} />;
}

function BackLink() {
  return (
    <Link href="/research" className="text-xs text-ink-3 hover:text-ink-2">
      ‹ Research
    </Link>
  );
}

// ------------------------------------------------------------------ no report yet

function NoReport({ symbol, engine, initialJob, onDone }: { symbol: string; engine: boolean; initialJob: Job | null; onDone: () => void }) {
  const done = useCallback(() => onDone(), [onDone]);
  const { job, error, start } = useJob(symbol, done);
  const j = job ?? initialJob;
  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <BackLink />
        <h1 className="text-xl font-semibold tracking-[0.01em]">{symbol}</h1>
      </header>
      {!j && (
        <section className="max-w-xl space-y-3">
          <p className="text-sm text-ink-2">No research has been built for {symbol} yet.</p>
          {engine ? (
            <>
              <p className="text-sm text-ink-2">
                FINN will check the ticker on NSE, find the company&apos;s last four results filings, call transcripts, presentations and annual report on BSE and NSE, and
                read them. This usually takes under a minute.
              </p>
              <button type="button" onClick={() => void start()} className="h-9 rounded-md bg-brass px-4 text-sm font-medium text-base hover:bg-brass/90">
                Research {symbol}
              </button>
            </>
          ) : (
            <div className="space-y-2 rounded-md border border-line bg-surface p-3 text-sm text-ink-2">
              <p>The research engine isn&apos;t connected to this app, so reports can&apos;t be built from here. To build one:</p>
              <pre className="num overflow-x-auto rounded bg-base p-2 text-xs text-ink">python -m finn_engine research {symbol}</pre>
              <p className="text-xs text-ink-3">Or run <code>python -m finn_engine serve</code> and set FINN_ENGINE_URL so this button works on demand.</p>
            </div>
          )}
          {error && <p className="text-sm text-down">{error}</p>}
        </section>
      )}
      {j && <JobView job={j} onRetry={() => void start()} engine={engine} />}
    </div>
  );
}

function JobView({ job, onRetry, engine }: { job: Job; onRetry: () => void; engine: boolean }) {
  const at = STAGES.findIndex(([k]) => k === job.stage);
  if (job.status === "error" && job.error) {
    const e = job.error;
    const failed = (e.fetch_log ?? []).filter((l) => !l.ok);
    return (
      <section className="max-w-2xl space-y-3" aria-live="polite">
        <p className="text-sm font-medium text-down">{e.message}</p>
        {e.identity && (
          <p className="text-sm text-ink-2">
            {e.identity.name}
            {e.identity.isin ? <span className="text-ink-3">, ISIN {e.identity.isin}</span> : null}
          </p>
        )}
        {e.identity?.notes?.map((n) => (
          <p key={n} className="text-xs text-ink-3">{n}</p>
        ))}
        {failed.length > 0 && (
          <div className="space-y-1 rounded-md border border-line bg-surface p-3">
            <p className="text-xs text-ink-2">Sources that couldn&apos;t be reached</p>
            {failed.map((l, i) => (
              <p key={i} className="num text-2xs text-ink-3">
                {l.source.toUpperCase()} {l.target}: {(l.error ?? "").slice(0, 120)}
              </p>
            ))}
          </div>
        )}
        <p className="text-xs text-ink-3">Nothing has been filled in from other sources. Try again when the exchanges are reachable.</p>
        {engine && (
          <button type="button" onClick={onRetry} className="h-8 rounded-md border border-line-strong px-3 text-xs text-ink hover:border-brass">
            Try again
          </button>
        )}
      </section>
    );
  }
  return (
    <section className="max-w-xl space-y-3" aria-live="polite" aria-busy={job.status !== "done"}>
      <p className="text-sm text-ink-2">Researching {job.symbol}…</p>
      <ol className="space-y-1.5">
        {STAGES.map(([k, label], i) => (
          <li key={k} className={`flex items-center gap-2 text-sm ${i < at ? "text-ink-2" : i === at ? "text-ink" : "text-ink-3"}`}>
            <span aria-hidden className={`h-1.5 w-1.5 rounded-full ${i < at ? "bg-up" : i === at ? "animate-pulse bg-brass" : "bg-line-strong"}`} />
            {label}
          </li>
        ))}
      </ol>
    </section>
  );
}

// ------------------------------------------------------------------ report

function ReportView({ r, engine, onRefreshed }: { r: Report; engine: boolean; onRefreshed: () => void }) {
  const idn = r.identity;
  const done = useCallback(() => onRefreshed(), [onRefreshed]);
  const { job, start } = useJob(idn.symbol, done);
  const running = job && (job.status === "queued" || job.status === "running");
  return (
    <div className="space-y-8">
      <header className="space-y-3">
        <BackLink />
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="min-w-0">
            <h1 className="text-xl font-semibold tracking-[0.01em]">{idn.symbol}</h1>
            <p className="text-sm text-ink-2">
              {idn.name}
              {idn.industry ? <span className="text-ink-3">, {idn.industry}</span> : null}
            </p>
          </div>
          <Price symbol={idn.symbol} />
        </div>
        <p className="text-xs text-ink-3">
          Primary sources only, as of {r.as_of}: {r.counts.documents.results} results filing{r.counts.documents.results === 1 ? "" : "s"}, {r.counts.documents.transcript} call transcript{r.counts.documents.transcript === 1 ? "" : "s"},{" "}
          {r.counts.documents.presentation} presentation{r.counts.documents.presentation === 1 ? "" : "s"}, {r.counts.documents.annual_report ? "the annual report" : "no annual report"}. Built {dayIST(r.generated_at)}{" "}
          {timeIST(r.generated_at)} IST.
          {engine && (
            <button type="button" disabled={Boolean(running)} onClick={() => void start()} className="ml-2 text-brass hover:underline disabled:text-ink-3 disabled:no-underline">
              {running ? `Refreshing (${job?.stage ?? "queued"})…` : "Refresh"}
            </button>
          )}
          {job?.status === "error" && <span className="ml-2 text-down">Refresh failed: {job.error?.message}</span>}
        </p>
        {r.dataset === "fixture" && (
          <p role="note" className="rounded-md border border-alert/40 bg-alert/5 px-3 py-2 text-xs text-alert">
            Synthetic test company. {idn.name} and every document behind this page are fictional, generated to test the pipeline. None of it is a real filing.
          </p>
        )}
        {idn.notes.length > 0 && <Gaps gaps={idn.notes.map((n) => ({ area: "Identity", detail: n }))} />}
      </header>

      <AskFinn r={r} engine={engine} />
      <NvnSummary r={r} />
      <CredibilityCard r={r} />

      {r.gaps.length > 0 && (
        <div className="space-y-1">
          <p className="text-xs font-medium text-ink-2">What&apos;s missing</p>
          <Gaps gaps={r.gaps} />
        </div>
      )}

      <nav aria-label="Sections" className="sticky top-[var(--topbar,0px)] z-20 lg:top-0 -mx-4 overflow-x-auto border-b border-line bg-base/95 px-4 py-2 backdrop-blur no-scrollbar sm:mx-0 sm:px-0">
        <ul className="flex gap-1.5">
          {SECTIONS.map(([id, label]) => (
            <li key={id}>
              <a href={`#${id}`} className={`inline-flex h-7 items-center whitespace-nowrap rounded-md border px-2.5 text-xs ${id === "nvn" || id === "ask" ? "border-brass/50 text-brass" : "border-line text-ink-2"} hover:border-brass/60 hover:text-ink`}>
                {label}
              </a>
            </li>
          ))}
        </ul>
      </nav>

      <Block id="business" title="1. Business snapshot"><Business r={r} /></Block>
      <Block id="snapshot" title="2. Financial snapshot"><Snapshot r={r} /></Block>
      <Block id="trajectory" title="3. Financial trajectory"><Trajectory r={r} /></Block>
      <Block id="balance" title="4. Balance sheet"><BalanceSheet r={r} /></Block>
      <Block id="cash" title="5. Cash quality"><CashQuality r={r} /></Block>
      <Block id="nvn" title="6. Narrative vs Numbers"><NarrativeVsNumbers r={r} /></Block>
      <Block id="guidance" title="7. Management guidance"><Guidance r={r} /></Block>
      <Block id="bullbear" title="8. Bull vs Bear"><BullBear r={r} /></Block>
      <Block id="sources" title="Sources"><Sources r={r} /></Block>
    </div>
  );
}

function Block({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section aria-labelledby={`${id}-h`} id={id} className="scroll-mt-[calc(var(--topbar,0px)_+_3.5rem)] space-y-4 lg:scroll-mt-16">
      <SectionHead id={`${id}-h`} title={title} />
      {children}
    </section>
  );
}

function Price({ symbol }: { symbol: string }) {
  // Prices come from the push feed's end-of-day data when it covers this company.
  const f = useFeed();
  const fc = f.status === "ready" ? companyOf(f.feed, symbol) : undefined;
  const sig = f.status === "ready" ? f.feed.market.find((m) => m.symbol === symbol)?.signal : undefined;
  if (!fc || fc.closes.length < 2 || !sig) return null;
  const closes = fc.closes.map((p) => p.adj_close);
  return (
    <div className="flex items-end gap-4">
      <Sparkline values={closes} width={96} height={30} label="Recent closing prices" />
      <div className="text-right">
        <p className="num text-md font-medium">₹{rupees(sig.close)}</p>
        <p className="num text-xs">
          <span className={signClass(sig.ret_1d ?? 0)}>{pct(sig.ret_1d ?? 0)}</span>
          <span className="text-ink-3"> on {fc.eod.last ?? "last close"}{f.status === "ready" && f.feed.dataset === "fixture" ? ", synthetic prices" : ""}</span>
        </p>
      </div>
    </div>
  );
}
