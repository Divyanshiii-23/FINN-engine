"use client";

import Link from "next/link";
import { useState } from "react";
import type { Feed, FeedEvent } from "@/lib/feed";
import { companyOf, eventById } from "@/lib/feed";
import { CATEGORY_LABEL } from "@/lib/taxonomy";
import { placeEvent } from "@/lib/push";
import { dateTimeIST, multiple, pct, signClass } from "@/lib/format";
import { useStore } from "@/lib/store";
import { DatasetBadge, FeedGate, SourceLinks } from "./FeedGate";
import { FeedResultsTable } from "./FeedResultsTable";
import { Chevron, ClassTag, SectionHead, TextButton } from "../ui/primitives";

const PREFIX = /^.*?\s-\s\d{6}\s-\s/;

export function EventDetailScreen({ id }: { id: string }) {
  return (
    <FeedGate>
      {(feed) => {
        const e = eventById(feed, id);
        return e ? <EventDetail feed={feed} e={e} /> : <NotFound />;
      }}
    </FeedGate>
  );
}

function NotFound() {
  return (
    <div className="space-y-2">
      <Link href="/" className="text-xs text-ink-3 hover:text-ink-2">‹ Brief</Link>
      <p className="text-md">This event isn&apos;t in the current feed.</p>
      <p className="text-sm text-ink-2">It may be older than the feed&apos;s 30-day window, or the feed was regenerated.</p>
    </div>
  );
}

function Tier({ tier }: { tier: string }) {
  const cls = tier === "interrupt" ? "border-alert/50 text-alert" : tier === "brief" ? "border-line-strong text-ink-2" : "border-line text-ink-3";
  const label = tier === "interrupt" ? "Needs you" : tier === "brief" ? "Worth a look" : "Routine";
  return <span className={`inline-flex h-5 items-center rounded-[4px] border px-1.5 text-2xs font-medium ${cls}`}>{label}</span>;
}

function EventDetail({ feed, e }: { feed: Feed; e: FeedEvent }) {
  const { rules } = useStore();
  const placed = placeEvent(e, rules);
  const m = e.materiality;
  const c = companyOf(feed, e.symbol);
  return (
    <div className="space-y-8">
      <header className="space-y-2">
        <Link href="/" className="text-xs text-ink-3 hover:text-ink-2">‹ Brief</Link>
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-xl font-semibold tracking-[0.01em]">{e.symbol}</h1>
          <Tier tier={placed.tier} />
          {e.fixture && <DatasetBadge dataset="fixture" />}
        </div>
        <p className="text-sm text-ink-2">
          {c?.name ?? e.symbol}. {CATEGORY_LABEL[e.category]}
          {e.subtype && <span className="text-ink-3">, {e.subtype.replace(/_/g, " ")}</span>}
        </p>
        <p className="num text-xs text-ink-3">
          Filed {dateTimeIST(e.first_filed_at)}
          {e.last_filed_at !== e.first_filed_at && ` to ${dateTimeIST(e.last_filed_at)}`}
        </p>
      </header>

      <section aria-labelledby="ex" className="space-y-3">
        <SectionHead id="ex" title="What happened, and why it matters" />
        <p className="text-md leading-snug text-ink">{e.explanation.what}</p>
        <p className="text-sm text-ink-2">{e.explanation.why}</p>
        <p className="text-2xs text-ink-3">
          {e.explanation.generator === "template"
            ? "Written by FINN's template from extracted facts and computed figures; no language model was used."
            : `Phrased by ${e.explanation.generator.replace("llm:", "")} from extracted facts only, then checked: every number in it appears in the inputs.`}
          {e.explanation.rejected_llm_reason && ` A model draft was rejected (${e.explanation.rejected_llm_reason}), so the template text is shown.`}
        </p>
      </section>

      <Materiality e={e} feed={feed} ruleNote={placed.floorApplied ? `Shown despite your category rule: ${m.floor?.toLowerCase()}.` : placed.ruleApplied ? `Your rule for ${CATEGORY_LABEL[e.category].toLowerCase()} moves this to "${placed.tier}".` : null} />

      {e.results && (
        <section aria-labelledby="res" className="space-y-3">
          <SectionHead id="res" title="Results figures" />
          <FeedResultsTable r={e.results} showChecks />
          <p className="text-2xs text-ink-3">Hover or focus a figure to see the row of the filing it came from. QoQ and YoY are computed in code from the three columns of the same statement.</p>
        </section>
      )}

      <section aria-labelledby="mkt" className="space-y-2">
        <SectionHead id="mkt" title="Market reaction" action={<Link href={`/moves/${e.symbol}`} className="text-xs text-brass hover:underline">Price and volume</Link>} />
        {e.reaction ? (
          <p className="num text-sm text-ink-2">
            Session of {e.reaction.date}: <span className={signClass(e.reaction.ret_1d)}>{pct(e.reaction.ret_1d)}</span>
            {e.reaction.ret_z !== null && <span className="text-ink-3"> ({e.reaction.ret_z >= 0 ? "+" : ""}{e.reaction.ret_z.toFixed(1)} standard deviations)</span>}
            {e.reaction.vol_ratio_20d !== null && `, volume ${multiple(e.reaction.vol_ratio_20d)} its 20-day average`}
            {e.reaction.split_or_bonus_on_date && ". Split or bonus that day: price move not scored."}
          </p>
        ) : (
          <p className="text-sm text-ink-3">
            {c?.eod.available ? "Not yet in the price data: the filing came after the latest session's close." : "No price data for this company on the last run."}
          </p>
        )}
      </section>

      <Filings e={e} />

      <Classification e={e} />
    </div>
  );
}

function Materiality({ e, feed, ruleNote }: { e: FeedEvent; feed: Feed; ruleNote: string | null }) {
  const [open, setOpen] = useState<string | null>(null);
  const m = e.materiality;
  return (
    <section aria-labelledby="mat" className="space-y-3">
      <SectionHead id="mat" title="How FINN scored this" count={`${m.score} / 100`} />
      <table className="w-full text-sm">
        <caption className="sr-only">Materiality components</caption>
        <thead>
          <tr className="border-b border-line text-2xs text-ink-3">
            <th scope="col" className="py-1.5 text-left font-normal">Component</th>
            <th scope="col" className="w-16 py-1.5 text-right font-normal">Points</th>
          </tr>
        </thead>
        <tbody>
          {m.components.map((c) => {
            const hasInputs = Object.keys(c.inputs ?? {}).length > 0;
            const isOpen = open === c.code;
            return (
              <tr key={c.code} className="border-b border-line/60 align-top">
                <td className="py-2 pr-3">
                  <p className="text-ink">{c.label}</p>
                  <p className="text-xs text-ink-2">{c.detail}</p>
                  {hasInputs && (
                    <div className="-ml-2">
                      <TextButton onClick={() => setOpen(isOpen ? null : c.code)} aria-expanded={isOpen}>
                        <Chevron open={isOpen} /> Inputs
                      </TextButton>
                    </div>
                  )}
                  {isOpen && (
                    <dl className="num mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-2xs">
                      {Object.entries(c.inputs).map(([k, v]) => (
                        <div key={k} className="contents">
                          <dt className="text-ink-3">{k}</dt>
                          <dd className="break-all text-ink-2">{v === null ? "none" : String(v)}</dd>
                        </div>
                      ))}
                    </dl>
                  )}
                </td>
                <td className={`num py-2 text-right ${c.points > 0 ? "text-ink" : c.points < 0 ? "text-down" : "text-ink-3"}`}>
                  {c.points > 0 && c.code !== "type" ? "+" : ""}
                  {c.points}
                </td>
              </tr>
            );
          })}
        </tbody>
        <tfoot>
          <tr>
            <th scope="row" className="py-2 text-left font-medium">Score</th>
            <td className="num py-2 text-right font-semibold">{m.score}</td>
          </tr>
        </tfoot>
      </table>
      <p className="text-2xs text-ink-3">
        {feed.thresholds.interrupt}+ needs you, {feed.thresholds.brief}+ worth a look, below that routine. Scores are clamped to 0–100. Scoring {m.version}.
        {ruleNote && ` ${ruleNote}`}
      </p>
    </section>
  );
}

function Filings({ e }: { e: FeedEvent }) {
  const byId = new Map(e.announcements.map((a) => [a.id, a]));
  return (
    <section aria-labelledby="fil" className="space-y-2">
      <SectionHead id="fil" title="Filings" count={e.announcements.length} />
      {e.attachment && e.attachment.status !== "ok" && (
        <p className="text-xs text-alert">
          {e.attachment.status === "unavailable" ? `Attachment unavailable: ${e.attachment.note}. Nothing was inferred in its place.` : e.attachment.note}
        </p>
      )}
      <ol className="space-y-3">
        {e.announcements.map((a) => (
          <li key={a.id} className={`border-l-2 pl-3 ${a.duplicate_of ? "border-line" : "border-line-strong"}`}>
            <p className={`text-sm ${a.duplicate_of ? "text-ink-3" : "text-ink"}`}>{a.subject.replace(PREFIX, "")}</p>
            {a.headline && <p className="text-xs text-ink-2">{a.headline}</p>}
            <dl className="num mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-2xs">
              <dt className="text-ink-3">Filed</dt>
              <dd className="text-ink-2">{dateTimeIST(a.filed_at)}</dd>
              <dt className="text-ink-3">Source</dt>
              <dd className="text-ink-2">{a.source.source.toUpperCase()} id {a.source.source_id}{a.exchange_subcategory ? `, ${a.exchange_subcategory}` : ""}</dd>
              <dt className="text-ink-3">Fetched</dt>
              <dd className="text-ink-2">{dateTimeIST(a.source.fetched_at)}</dd>
              {a.source.raw_path && (
                <>
                  <dt className="text-ink-3">Raw payload</dt>
                  <dd className="break-all text-ink-3">{a.source.raw_path.split("/").slice(-3).join("/")}</dd>
                </>
              )}
            </dl>
            {a.duplicate_of && <p className="mt-1 text-2xs text-ink-3">Duplicate, merged: {a.duplicate_reason}.</p>}
            {a.supersedes && <p className="mt-1 text-2xs text-alert">Revision of: {byId.get(a.supersedes)?.subject.replace(PREFIX, "") ?? a.supersedes}.</p>}
            <div className="mt-1"><SourceLinks source={a.source} /></div>
          </li>
        ))}
      </ol>
    </section>
  );
}

function Classification({ e }: { e: FeedEvent }) {
  const k = e.classification;
  const facts = Object.entries(e.facts).filter(([, v]) => v !== null && !(Array.isArray(v) && v.length === 0));
  return (
    <section aria-labelledby="cls" className="space-y-2">
      <SectionHead id="cls" title="Classification and extracted facts" />
      <dl className="num grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-xs">
        <dt className="text-ink-3">Category</dt>
        <dd className="text-ink-2">{CATEGORY_LABEL[e.category]}{k.subtype ? `, ${k.subtype.replace(/_/g, " ")}` : ""}</dd>
        <dt className="text-ink-3">Method</dt>
        <dd className="text-ink-2">{k.method === "rule" ? `Rule ${k.rule_id}` : "No rule matched (fallback)"}, {k.confidence} confidence</dd>
        {k.matched && (
          <>
            <dt className="text-ink-3">Matched text</dt>
            <dd className="text-ink-2">&ldquo;{k.matched}&rdquo;</dd>
          </>
        )}
        {facts.map(([key, v]) => (
          <div key={key} className="contents">
            <dt className="text-ink-3">{key.replace(/_/g, " ")}</dt>
            <dd className="text-ink-2">{Array.isArray(v) ? v.map((x) => (typeof x === "object" ? Object.values(x as object).filter(Boolean).join(" ") : String(x))).join("; ") : String(v)}</dd>
          </div>
        ))}
      </dl>
      <ClassTag kind="reported">Facts are copied from the filing text by pattern; nothing is inferred</ClassTag>
    </section>
  );
}
