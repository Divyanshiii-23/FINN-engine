"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useStore } from "@/lib/store";
import type { Feed } from "@/lib/feed";
import { buildBrief, computeAlerts, type WindowKey } from "@/lib/push";
import { CATEGORY_LABEL } from "@/lib/taxonomy";
import { dateTimeIST, relativeStamp } from "@/lib/format";
import { PushEventRow } from "../push/PushEventRow";
import { FeedGate } from "../push/FeedGate";
import { AlertRow } from "../alerts/AlertRow";
import { Chevron, Segmented, SectionHead, TextButton } from "../ui/primitives";

const WINDOWS: { value: WindowKey; label: string }[] = [
  { value: "since", label: "Since last look" },
  { value: "24h", label: "24 h" },
  { value: "3d", label: "3 days" },
  { value: "7d", label: "7 days" },
];

export function BriefScreen() {
  return <FeedGate>{(feed) => <Brief feed={feed} />}</FeedGate>;
}

function Brief({ feed }: { feed: Feed }) {
  const { rules, lastLooked, triage, markAllSeen, setTriage } = useStore();
  const [win, setWin] = useState<WindowKey>("since");
  const [openGroup, setOpenGroup] = useState<string | null>(null);
  const [showAside, setShowAside] = useState(false);

  const brief = useMemo(() => buildBrief(feed, win, lastLooked, rules, triage), [feed, win, lastLooked, rules, triage]);
  const market = useMemo(() => computeAlerts(feed, rules).filter((a) => a.kind !== "event"), [feed, rules]);

  const filingsOf = (xs: { event: { announcements: { duplicate_of: string | null }[] } }[]) =>
    xs.reduce((n, p) => n + p.event.announcements.filter((a) => !a.duplicate_of).length, 0);
  const needF = filingsOf(brief.needsYou);
  const worthF = filingsOf(brief.worthALook);
  const restF = Math.max(0, brief.filings - needF - worthF);
  const routineN = brief.routine.reduce((n, g) => n + g.items.length, 0);
  const quiet = brief.needsYou.length === 0 && brief.worthALook.length === 0;
  const mainRows = [brief.needsYou.length, brief.worthALook.length, brief.routine.length, brief.setAside.length].filter(Boolean).length || 1;
  const title = win === "since" ? "Since you last looked" : `Last ${WINDOWS.find((w) => w.value === win)!.label}`;
  const gaps = feed.unavailable.filter((u) => u.source === "bse" || u.source === "nse");

  return (
    <div className="space-y-8">
      <section aria-labelledby="brief-head" className="space-y-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h1 id="brief-head" className="text-sm font-medium text-ink-2">{title}</h1>
            <p className="num mt-0.5 text-xs text-ink-3">
              {dateTimeIST(brief.since)} to {dateTimeIST(brief.until)}
            </p>
          </div>
          <div className="-mx-4 overflow-x-auto px-4 no-scrollbar sm:mx-0 sm:px-0">
            <Segmented label="Time window" value={win} onChange={setWin} options={WINDOWS} />
          </div>
        </div>

        <p className="text-xl font-light tracking-[-0.01em] text-ink-2">
          <span className="num">{brief.filings}</span> filings
          <span aria-hidden className="mx-2.5 text-ink-3">→</span>
          <span className="sr-only">, of which </span>
          <span className={`num font-semibold ${brief.needsYou.length ? "text-ink" : "text-ink-2"}`}>{brief.needsYou.length}</span>
          <span className="text-ink"> need you</span>
        </p>

        {brief.filings > 0 && (
          <div className="space-y-2">
            <div className="flex h-1.5 gap-[2px] overflow-hidden rounded-full" aria-hidden>
              {needF > 0 && <span className="bg-alert" style={{ flexGrow: needF }} />}
              {worthF > 0 && <span className="bg-ink-3" style={{ flexGrow: worthF }} />}
              {restF > 0 && <span className="bg-line-strong" style={{ flexGrow: restF }} />}
            </div>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <ul className="num flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2">
                <li className="flex items-center gap-1.5"><span aria-hidden className="h-2 w-2 rounded-full bg-alert" />{needF} in events that need you</li>
                <li className="flex items-center gap-1.5"><span aria-hidden className="h-2 w-2 rounded-full bg-ink-3" />{worthF} worth a look</li>
                <li className="flex items-center gap-1.5"><span aria-hidden className="h-2 w-2 rounded-full bg-line-strong" />{restF} routine or set aside</li>
                {brief.duplicatesMerged > 0 && <li className="text-ink-3">{brief.duplicatesMerged} duplicate {brief.duplicatesMerged === 1 ? "copy" : "copies"} merged</li>}
              </ul>
              {win === "since" && !quiet && (
                <TextButton tone="accent" onClick={() => markAllSeen(feed.as_of)}>Mark all as seen</TextButton>
              )}
            </div>
          </div>
        )}

        {gaps.length > 0 && (
          <p className="rounded-md border border-alert/40 px-3 py-2 text-xs text-ink-2">
            <span className="font-medium text-alert">Filings may be missing</span> for {gaps.map((g) => g.symbol).join(", ")}: the announcements
            source couldn&apos;t be read on the last run.{" "}
            <Link href="/alerts?tab=sources" className="text-brass hover:underline">Source status</Link>
          </p>
        )}
      </section>

      {quiet && (
        <section className="rounded-lg border border-line bg-surface px-4 py-6">
          <p className="text-md text-ink">Nothing needs you {win === "since" ? `since ${dateTimeIST(brief.since)}` : "in this window"}.</p>
          <p className="mt-1 text-sm text-ink-2">
            {routineN > 0 ? `${routineN} routine ${routineN === 1 ? "filing" : "filings"} arrived and ${routineN === 1 ? "is" : "are"} collapsed below.` : "No filings arrived across your holdings."}
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {win !== "24h" && <TextButton tone="accent" onClick={() => setWin("24h")}>Show the last 24 hours</TextButton>}
            {win !== "7d" && <TextButton tone="accent" onClick={() => setWin("7d")}>Show the last 7 days</TextButton>}
          </div>
        </section>
      )}

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-[minmax(0,1fr)_300px] lg:items-start lg:gap-x-10" style={{ "--rows": mainRows } as React.CSSProperties}>
        {brief.needsYou.length > 0 && (
          <section aria-labelledby="needs-you" className="min-w-0 lg:col-start-1">
            <SectionHead id="needs-you" title="Needs you" count={brief.needsYou.length} />
            <div>{brief.needsYou.map((p) => <PushEventRow key={p.event.id} p={p} feed={feed} />)}</div>
          </section>
        )}

        <aside className="min-w-0 space-y-8 lg:col-start-2 lg:[grid-row:1/span_var(--rows)]" aria-label="Market moves">
          <section aria-labelledby="moves">
            <SectionHead
              id="moves"
              title="End-of-day moves"
              count={market.length}
              action={<Link href="/alerts?tab=rules" className="text-xs text-brass hover:underline">Thresholds</Link>}
            />
            {market.length === 0 ? (
              <p className="py-3 text-xs text-ink-3">
                No holding moved more than ±{rules.priceMovePct}% or traded above {rules.volumeMultiple}× its 20-day volume.
              </p>
            ) : (
              <div>{[...market].sort((a, b) => Number(Boolean(a.explained)) - Number(Boolean(b.explained))).map((a) => <AlertRow key={a.key} a={a} feed={feed} withActions={false} />)}</div>
            )}
            <p className="mt-2 text-2xs text-ink-3">
              {feed.eod_date ? `Session of ${new Date(`${feed.eod_date}T12:00:00Z`).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}. ` : "No price data on the last run. "}
              Checked once after the close against end-of-day prices.
            </p>
          </section>
          <section aria-labelledby="legend" className="hidden lg:block">
            <SectionHead id="legend" title="How FINN ranks filings" />
            <p className="mt-2 text-xs text-ink-2">
              Each filing gets a score from its type, its size relative to the company, results figures, and the market&apos;s reaction.
              Scores of {feed.thresholds.interrupt} or more need you; {feed.thresholds.brief} or more are worth a look. Open any item to see every component.
            </p>
          </section>
        </aside>

        {brief.worthALook.length > 0 && (
          <section aria-labelledby="worth" className="min-w-0 lg:col-start-1">
            <SectionHead id="worth" title="Worth a look" count={brief.worthALook.length} />
            <div>{brief.worthALook.map((p) => <PushEventRow key={p.event.id} p={p} feed={feed} compact />)}</div>
          </section>
        )}

        {brief.routine.length > 0 && (
          <section aria-labelledby="routine" className="min-w-0 lg:col-start-1">
            <SectionHead id="routine" title="Routine, collapsed" count={routineN} />
            <ul>
              {brief.routine.map((g) => {
                const open = openGroup === g.category;
                return (
                  <li key={g.category} className="border-b border-line last:border-b-0">
                    <button type="button" onClick={() => setOpenGroup(open ? null : g.category)} aria-expanded={open} className="flex h-10 w-full items-center gap-2 text-left text-sm text-ink-2 hover:text-ink">
                      <span className="text-ink-3"><Chevron open={open} /></span>
                      <span className="flex-1">{CATEGORY_LABEL[g.category]}</span>
                      <span className="num text-xs text-ink-3">{g.items.length}</span>
                    </button>
                    {open && (
                      <ul className="space-y-1.5 pb-3 pl-5">
                        {g.items.map((p) => (
                          <li key={p.event.id} className="flex items-baseline gap-3 text-xs">
                            <span className="w-20 shrink-0 font-semibold text-ink-2">{p.event.symbol}</span>
                            <Link href={`/events/${p.event.id}`} className="min-w-0 flex-1 text-ink-3 hover:text-ink">{p.event.explanation.what}</Link>
                            <span className="num shrink-0 text-2xs text-ink-3">{relativeStamp(p.at, feed.as_of)}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </li>
                );
              })}
            </ul>
          </section>
        )}

        {brief.setAside.length > 0 && (
          <section aria-labelledby="set-aside" className="min-w-0 lg:col-start-1">
            <SectionHead
              id="set-aside"
              title="Set aside"
              count={brief.setAside.length}
              action={<TextButton onClick={() => setShowAside((v) => !v)} aria-expanded={showAside}>{showAside ? "Hide" : "Show"}</TextButton>}
            />
            {showAside && (
              <ul>
                {brief.setAside.map((p) => (
                  <li key={p.event.id} className="flex items-baseline justify-between gap-3 border-b border-line py-2.5 last:border-b-0">
                    <div className="min-w-0">
                      <p className="text-xs text-ink-3">
                        <span className="font-semibold text-ink-2">{p.event.symbol}</span> {triage[p.event.id] === "noted" ? "marked noted" : "snoozed"}
                      </p>
                      <p className="truncate text-sm text-ink-2">{p.event.explanation.what}</p>
                    </div>
                    <TextButton onClick={() => setTriage(p.event.id, null)}>Restore</TextButton>
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}
      </div>
    </div>
  );
}
