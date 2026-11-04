"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useId, useMemo, useRef, useState } from "react";
import { useIndex, useSecurities, type IndexEntry, type Security } from "@/lib/research";
import { SectionHead } from "../ui/primitives";

const TICKER = /^[A-Z0-9][A-Z0-9&-]{0,19}$/;

export function ResearchHome() {
  const router = useRouter();
  const listId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [q, setQ] = useState("");
  const [cursor, setCursor] = useState(0);
  const { rows, busy } = useSecurities(q);
  const index = useIndex();
  const built = useMemo(() => new Map((index ?? []).map((c) => [c.symbol, c])), [index]);
  const typed = q.trim().toUpperCase().replace(/^(NSE|BSE)\s*:\s*/, "").replace(/\.(NS|BO)$/, "").trim();
  const exactListed = rows.some((r) => r.symbol === typed);

  const go = (symbol: string) => router.push(`/research/${encodeURIComponent(symbol)}`);

  return (
    <div className="space-y-8">
      <header className="space-y-1">
        <h1 className="text-lg font-semibold">Research</h1>
        <p className="max-w-[62ch] text-sm text-ink-2">
          Any NSE-listed company, read from its own filings: quarterly results, earnings-call transcripts, investor presentations and the annual report. No news,
          broker notes or model knowledge. Every figure and quote opens the page it came from.
        </p>
      </header>

      <div className="relative max-w-xl">
        <label htmlFor={`${listId}-input`} className="sr-only">
          Search NSE tickers or company names
        </label>
        <div className="flex h-11 items-center gap-2 rounded-lg border border-line-strong bg-surface px-3 focus-within:border-brass">
          <svg aria-hidden width="16" height="16" viewBox="0 0 20 20" className="text-ink-3">
            <circle cx="9" cy="9" r="5" fill="none" stroke="currentColor" strokeWidth="1.5" />
            <path d="M13 13l3.5 3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
          <input
            ref={inputRef}
            id={`${listId}-input`}
            role="combobox"
            aria-expanded={q.trim().length > 0}
            aria-controls={`${listId}-list`}
            aria-activedescendant={rows[cursor] ? `${listId}-${rows[cursor].symbol}` : undefined}
            autoComplete="off"
            spellCheck={false}
            placeholder="NSE ticker or company name"
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setCursor(0);
            }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setCursor((i) => Math.min(i + 1, rows.length - 1));
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setCursor((i) => Math.max(i - 1, 0));
              } else if (e.key === "Enter") {
                if (rows[cursor]) go(rows[cursor].symbol);
                else if (TICKER.test(typed)) go(typed);
              } else if (e.key === "Escape") {
                setQ("");
              }
            }}
            className="h-full flex-1 bg-transparent text-md text-ink placeholder:text-ink-3 focus:outline-none"
          />
          {q && (
            <button type="button" onClick={() => { setQ(""); inputRef.current?.focus(); }} className="text-xs text-ink-3 hover:text-ink" aria-label="Clear search">
              Clear
            </button>
          )}
        </div>
        {q.trim() && (
          <ul id={`${listId}-list`} role="listbox" className="absolute inset-x-0 top-12 z-20 overflow-hidden rounded-lg border border-line-strong bg-raised shadow-[0_12px_32px_-12px_rgba(0,0,0,0.6)]">
            {rows.map((r, i) => (
              <li
                key={r.symbol}
                id={`${listId}-${r.symbol}`}
                role="option"
                aria-selected={i === cursor}
                onMouseEnter={() => setCursor(i)}
                onMouseDown={(e) => {
                  e.preventDefault();
                  go(r.symbol);
                }}
                className={`flex cursor-pointer items-baseline gap-3 px-3 py-2.5 ${i === cursor ? "bg-surface" : ""}`}
              >
                <span className="w-28 shrink-0 truncate text-sm font-semibold tracking-[0.02em]">{r.symbol}</span>
                <span className="min-w-0 flex-1 truncate text-sm text-ink-2">{r.name}</span>
                <Status s={r} built={built.get(r.symbol)} />
              </li>
            ))}
            {!busy && rows.length === 0 && (
              <li className="px-3 py-3 text-sm text-ink-2" role="option" aria-selected={false} aria-disabled>
                No listed company matches “{q.trim()}”.
              </li>
            )}
            {TICKER.test(typed) && !exactListed && (
              <li
                role="option"
                aria-selected={false}
                onMouseDown={(e) => {
                  e.preventDefault();
                  go(typed);
                }}
                className="cursor-pointer border-t border-line px-3 py-2.5 text-xs text-ink-2 hover:bg-surface"
              >
                Try <span className="font-semibold text-ink">{typed}</span> anyway: NSE is checked when research runs, which catches listings newer than this list.
              </li>
            )}
          </ul>
        )}
      </div>

      <section aria-labelledby="reports" className="space-y-1">
        <SectionHead id="reports" title="Reports built" count={index?.length ?? ""} />
        {index && index.length === 0 && <p className="py-3 text-sm text-ink-2">None yet. Search for a ticker to research it.</p>}
        <ul>
          {(index ?? []).map((c) => (
            <ReportRow key={c.symbol} c={c} />
          ))}
        </ul>
      </section>

      <section aria-labelledby="how" className="grid grid-cols-1 gap-6 border-t border-line pt-6 text-sm text-ink-2 md:grid-cols-3">
        <h2 id="how" className="sr-only">
          How research is built
        </h2>
        <div className="space-y-1">
          <p className="font-medium text-ink">Read</p>
          <p>The latest four results filings, their call transcripts and presentations, and the latest annual report, found through BSE and NSE disclosures.</p>
        </div>
        <div className="space-y-1">
          <p className="font-medium text-ink">Separated</p>
          <p>Reported figures, management&apos;s explicit guidance, qualitative commentary and FINN&apos;s own calculations are kept apart and marked differently.</p>
        </div>
        <div className="space-y-1">
          <p className="font-medium text-ink">Checked</p>
          <p>Each target is compared with what was later reported, in code. Vague words (“healthy growth”) are kept as words and never turned into numbers.</p>
        </div>
      </section>
    </div>
  );
}

function Status({ s, built }: { s: Security; built?: IndexEntry }) {
  if (built) return <span className="shrink-0 text-2xs text-brass">Report as of {built.as_of}</span>;
  if (s.fixture) return <span className="shrink-0 text-2xs text-alert">Synthetic test company</span>;
  return <span className="shrink-0 text-2xs text-ink-3">Not researched</span>;
}

function ReportRow({ c }: { c: IndexEntry }) {
  const docs = Object.values(c.documents).reduce((a, b) => a + b, 0);
  return (
    <li className="border-b border-line">
      <Link href={`/research/${c.symbol}`} className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 py-2.5 hover:bg-surface">
        <span className="w-28 shrink-0 text-sm font-semibold tracking-[0.02em] text-ink">{c.symbol}</span>
        <span className="min-w-0 flex-1 truncate text-sm text-ink-2">
          {c.name}
          {c.industry && <span className="text-ink-3">, {c.industry}</span>}
        </span>
        <span className="num shrink-0 text-2xs text-ink-3">
          {docs} documents{c.flags ? <span className="text-alert">, {c.flags} flagged</span> : null}
        </span>
        {c.dataset === "fixture" && <span className="shrink-0 rounded-sm border border-alert/40 px-1 text-2xs text-alert">Synthetic</span>}
      </Link>
    </li>
  );
}
