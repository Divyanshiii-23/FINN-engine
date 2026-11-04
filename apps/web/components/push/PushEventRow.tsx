"use client";

import Link from "next/link";
import type { PlacedEvent } from "@/lib/push";
import type { Feed } from "@/lib/feed";
import { companyOf } from "@/lib/feed";
import { CATEGORY_LABEL } from "@/lib/taxonomy";
import { dateTimeIST, relativeStamp } from "@/lib/format";
import { useStore } from "@/lib/store";
import { FeedResultsTable } from "./FeedResultsTable";
import { SourceLinks } from "./FeedGate";
import { ClassMark, TextButton } from "../ui/primitives";

export function PushEventRow({ p, feed, compact = false }: { p: PlacedEvent; feed: Feed; compact?: boolean }) {
  const e = p.event;
  const { triage, setTriage } = useStore();
  const state = triage[e.id];
  const interrupt = p.tier === "interrupt";
  const primary = e.announcements.find((a) => !a.duplicate_of) ?? e.announcements[0];
  const filings = e.announcements.filter((a) => !a.duplicate_of).length;
  const dups = e.announcements.length - filings;
  const name = companyOf(feed, e.symbol)?.name ?? e.symbol;

  return (
    <article className="relative border-b border-line py-3.5 pl-4 pr-1 last:border-b-0" aria-labelledby={`${e.id}-t`}>
      <span aria-hidden className={`absolute bottom-3.5 left-0 top-3.5 w-[2px] rounded-full ${interrupt ? "bg-alert" : "bg-line-strong"}`} />
      <header className="flex items-baseline justify-between gap-3">
        <div className="flex min-w-0 items-baseline gap-2">
          <span className="text-sm font-semibold tracking-[0.02em] text-ink">{e.symbol}</span>
          <span className="truncate text-xs text-ink-3">
            {name}, {CATEGORY_LABEL[e.category]?.toLowerCase() ?? e.category}
          </span>
        </div>
        <time dateTime={e.last_filed_at} title={dateTimeIST(e.last_filed_at)} className="num shrink-0 text-2xs text-ink-3">
          {relativeStamp(e.last_filed_at, feed.as_of)}
        </time>
      </header>

      <h3 id={`${e.id}-t`} className={`mt-1 text-pretty ${compact ? "text-sm" : "text-md"} font-medium leading-snug text-ink`}>
        <Link href={`/events/${e.id}`} className="hover:text-brass">
          {e.explanation.what}
        </Link>
      </h3>
      <p className="mt-1 flex items-start gap-1.5 text-xs text-ink-2">
        <ClassMark kind="computed" className="mt-[3px] text-ink-3" />
        <span>
          {e.explanation.why}
          <span className="num ml-1.5 text-ink-3">Score {e.materiality.score}</span>
        </span>
      </p>
      {(p.floorApplied || p.ruleApplied) && (
        <p className="mt-1 text-2xs text-ink-3">
          {p.floorApplied ? `Shown despite your category setting: ${e.materiality.floor?.toLowerCase()}.` : `Placed here by your rule for ${CATEGORY_LABEL[e.category]?.toLowerCase()}.`}
        </p>
      )}

      {!compact && e.results && (e.category === "results") && (
        <div className="mt-3">
          <FeedResultsTable r={e.results} />
        </div>
      )}

      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
        <SourceLinks source={primary.source} compact />
        <span className="num text-2xs text-ink-3">
          {filings} {filings === 1 ? "filing" : "filings"}
          {dups > 0 && `, ${dups} duplicate${dups > 1 ? "s" : ""} merged`}
        </span>
      </div>

      <footer className="-ml-2 mt-1 flex flex-wrap items-center gap-x-1">
        <Link href={`/events/${e.id}`} className="inline-flex h-7 items-center rounded-md px-2 text-xs font-medium text-brass hover:bg-brass/10">
          Investigate
        </Link>
        {state ? (
          <TextButton onClick={() => setTriage(e.id, null)}>Undo {state === "noted" ? "noted" : "snooze"}</TextButton>
        ) : (
          <>
            <TextButton onClick={() => setTriage(e.id, "noted")}>Mark noted</TextButton>
            <TextButton onClick={() => setTriage(e.id, "snoozed")}>Snooze</TextButton>
          </>
        )}
      </footer>
    </article>
  );
}
