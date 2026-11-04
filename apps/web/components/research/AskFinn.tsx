"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { askFinn, DOC_KIND, factOf, openSource, type AskAnswer, type AskBlock, type Report } from "@/lib/research";
import { useStore } from "@/lib/store";
import { ClassMark, ClassTag } from "../ui/primitives";
import { Verdict } from "./report-ui";

const STATUS: Record<AskAnswer["status"], { label: string; cls: string }> = {
  answered: { label: "Answered from the documents", cls: "text-ink-2 border-line-strong" },
  partial: { label: "Partly answered", cls: "text-alert border-alert/45" },
  insufficient: { label: "Not enough evidence", cls: "text-down border-down/45" },
  out_of_scope: { label: "Outside what FINN answers", cls: "text-ink-3 border-line" },
};

/** Suggested questions, drawn from what this company's report actually contains. */
function suggestions(r: Report): string[] {
  const q = r.sections.snapshot.period;
  const out: string[] = [];
  const m = r.sections.snapshot.margins?.[0];
  const chg = m?.yoy_change ? factOf(m.yoy_change)?.value : undefined;
  if (!r.identity.is_financial && q) out.push(chg !== undefined && chg < 0 ? `Why did margins decline in ${q}?` : "How have margins moved over time?");
  if (r.sections.nvn.calls.length >= 2) out.push("What changed between the last two earnings calls?");
  out.push(r.identity.is_financial ? "How has asset quality changed?" : "Is operating cash flow supporting reported profits?");
  if (r.ledger.some((e) => e.metric === "capex")) out.push("What did management promise regarding capacity expansion?");
  else if (r.ledger.some((e) => e.kind === "guidance")) out.push("What has management guided for this year?");
  if (r.sections.nvn.discrepancies.some((d) => ["commentary_vs_numbers", "assertion_contradicted", "documents_disagree"].includes(d.rule)))
    out.push("Which financial indicators contradict management's narrative?");
  return out.slice(0, 5);
}

export function AskFinn({ r, engine }: { r: Report; engine: boolean }) {
  const sym = r.identity.symbol;
  const id = useId();
  // Answers cite fact ids from one report version; after a refresh they could point at
  // different figures, so history is kept per report and older versions are dropped.
  const key = `finn.ask.${sym}.${r.generated_at}`;
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<AskAnswer[]>([]);
  const input = useRef<HTMLTextAreaElement>(null);
  const sugg = useMemo(() => suggestions(r), [r]);

  useEffect(() => {
    try {
      for (let i = sessionStorage.length - 1; i >= 0; i--) {
        const k = sessionStorage.key(i);
        if (k && (k === `finn.ask.${sym}` || (k.startsWith(`finn.ask.${sym}.`) && k !== key))) sessionStorage.removeItem(k);
      }
      const raw = sessionStorage.getItem(key);
      setHistory(raw ? JSON.parse(raw) : []);
    } catch {
      /* storage unavailable: history lasts for the page only */
    }
  }, [key, sym]);
  useEffect(() => {
    try {
      sessionStorage.setItem(key, JSON.stringify(history.slice(0, 8)));
    } catch {
      /* ignore */
    }
  }, [history, key]);

  const submit = async (text: string) => {
    const question = text.trim();
    if (!question || busy) return;
    setBusy(true);
    setError(null);
    const res = await askFinn(sym, question);
    setBusy(false);
    if (res.ok) {
      setHistory((h) => [res.answer, ...h.filter((x) => x.question !== res.answer.question)]);
      setQ("");
      if (input.current) input.current.style.height = "";
    } else setError(res.message);
  };

  return (
    <section id="ask" aria-labelledby={`${id}-h`} className="scroll-mt-[calc(var(--topbar,0px)_+_3.5rem)] lg:scroll-mt-16 space-y-3 rounded-lg border border-line-strong bg-surface p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id={`${id}-h`} className="text-sm font-semibold">Ask FINN about {sym}</h2>
        <p className="text-2xs text-ink-3">Answers only from {sym}&apos;s filings, results, transcripts and presentations read for this report.</p>
      </div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void submit(q);
        }}
        className="flex items-end gap-2"
      >
        <label htmlFor={`${id}-q`} className="sr-only">Question about {sym}</label>
        <textarea
          id={`${id}-q`}
          ref={input}
          rows={1}
          maxLength={500}
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            const t = e.currentTarget; // grow with the question, up to about five lines
            t.style.height = "auto";
            t.style.height = `${Math.min(t.scrollHeight, 128)}px`;
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void submit(q);
            }
          }}
          placeholder={engine ? "e.g. Why did margins decline?" : "Ask FINN needs the research engine"}
          disabled={!engine || busy}
          className="min-h-10 flex-1 resize-none rounded-md border border-line-strong bg-base px-3 py-2 text-sm text-ink placeholder:text-ink-3 focus:border-brass focus:outline-none disabled:opacity-60"
        />
        <button type="submit" disabled={!engine || busy || !q.trim()} className="h-10 rounded-md bg-brass px-4 text-sm font-medium text-base hover:bg-brass/90 disabled:opacity-40">
          {busy ? "Reading…" : "Ask"}
        </button>
      </form>
      {!engine && (
        <p className="text-xs text-ink-3">
          Not connected: start <code>python -m finn_engine serve</code> and set FINN_ENGINE_URL, or run <code>python -m finn_engine ask {sym} &quot;question&quot;</code>.
        </p>
      )}
      {engine && history.length === 0 && (
        <ul className="flex flex-wrap gap-1.5" aria-label="Suggested questions">
          {sugg.map((s) => (
            <li key={s}>
              <button type="button" onClick={() => void submit(s)} disabled={busy} className="rounded-full border border-line px-2.5 py-1 text-xs text-ink-2 hover:border-brass/60 hover:text-ink">
                {s}
              </button>
            </li>
          ))}
        </ul>
      )}
      {error && <p className="text-sm text-down" role="alert">{error}</p>}
      <div className="space-y-5" aria-live="polite">
        {history.map((a, i) => (
          <AnswerView key={a.question + i} a={a} r={r} first={i === 0} onAsk={(s) => void submit(s)} suggestions={i === 0 ? sugg.filter((s) => s !== a.question).slice(0, 3) : []} />
        ))}
      </div>
    </section>
  );
}

function AnswerView({ a, r, first, onAsk, suggestions }: { a: AskAnswer; r: Report; first: boolean; onAsk: (q: string) => void; suggestions: string[] }) {
  const { openEvidence } = useStore();
  const [open, setOpen] = useState(first);
  // Number citations in order of first use, so the sources list reads like footnotes.
  const order = useMemo(() => {
    const ids: string[] = [];
    a.blocks.forEach((b) => b.cites.forEach((c) => !ids.includes(c) && ids.push(c)));
    return ids;
  }, [a]);
  const num = (c: string) => order.indexOf(c) + 1;
  const go = (c: string) => {
    const p = a.passages[c];
    if (p) openSource({ symbol: a.symbol, docId: p.doc_id, page: p.page, passageId: p.id });
    else openEvidence(c);
  };
  const st = STATUS[a.status];
  return (
    <article className="space-y-3 border-t border-line pt-4">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} className="flex w-full flex-wrap items-baseline justify-between gap-2 text-left">
        <span className="text-sm font-medium text-ink">{a.question}</span>
        <span className={`inline-flex h-5 items-center rounded-sm border px-1.5 text-2xs ${st.cls}`}>{st.label}</span>
      </button>
      {open && (
        <>
          <div className="space-y-3">
            {a.blocks.map((b, i) => (
              <Block key={i} b={b} a={a} num={num} go={go} />
            ))}
          </div>
          {order.length > 0 && <Sources a={a} r={r} order={order} go={go} />}
          <p className="text-2xs text-ink-3">
            {a.method === "rules" ? "Written by fixed rules from the cited evidence; no model." : a.method}
            {a.model_rejected ? ` A model answer was rejected (${a.model_rejected}).` : ""} As of {a.as_of}.
          </p>
          {suggestions.length > 0 && (
            <ul className="flex flex-wrap gap-1.5" aria-label="Follow-up questions">
              {suggestions.map((s) => (
                <li key={s}>
                  <button type="button" onClick={() => onAsk(s)} className="rounded-full border border-line px-2.5 py-1 text-xs text-ink-2 hover:border-brass/60 hover:text-ink">{s}</button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </article>
  );
}

function Marks({ ids, num, go }: { ids: string[]; num: (c: string) => number; go: (c: string) => void }) {
  return (
    <>
      {ids.map((c) => (
        <button key={c} type="button" onClick={() => go(c)} aria-label={`Source ${num(c)}`} className="num ml-0.5 align-super text-[10px] text-brass hover:underline">
          [{num(c)}]
        </button>
      ))}
    </>
  );
}

function Quote({ id, a, num, go }: { id: string; a: AskAnswer; num: (c: string) => number; go: (c: string) => void }) {
  const p = a.passages[id];
  const f = p ? null : factOf(id);
  const text = p?.text ?? f?.quote;
  if (!text) return null;
  const where = p ? [DOC_KIND[p.doc_kind], p.period, `p. ${p.page}`, p.speaker?.split(",")[0]].filter(Boolean).join(" · ") : [f?.label.split(":")[0], f?.period, f?.page ? `p. ${f.page}` : null, f?.speaker?.split(",")[0]].filter(Boolean).join(" · ");
  return (
    <figure className="space-y-0.5">
      {p?.question && <p className="text-2xs italic text-ink-3">In answer to {p.question.slice(0, 160)}{p.question.length > 160 ? "…" : ""}</p>}
      <blockquote className="border-l-2 border-line-strong pl-2.5 text-[13px] leading-relaxed text-ink">“{text}”</blockquote>
      <figcaption>
        <button type="button" onClick={() => go(id)} className="text-left text-2xs text-ink-3 underline decoration-dotted underline-offset-2 hover:text-brass">
          [{num(id)}] {where}
        </button>
      </figcaption>
    </figure>
  );
}

function Block({ b, a, num, go }: { b: AskBlock; a: AskAnswer; num: (c: string) => number; go: (c: string) => void }) {
  if (b.kind === "management" || b.kind === "table")
    return (
      <div className="space-y-2">
        <p className="text-xs text-ink-2"><ClassTag kind={b.info === "outlook" ? "outlook" : "assertion"}>{b.kind === "table" ? "Statement page" : "Management said"}</ClassTag> <span className="ml-1">{b.text}</span></p>
        <div className="space-y-2.5 pl-1">
          {b.cites.map((c) => <Quote key={c} id={c} a={a} num={num} go={go} />)}
        </div>
      </div>
    );
  if (b.kind === "interpretation")
    return (
      <p className="flex gap-2 font-serif text-[14.5px] leading-relaxed text-ink">
        <ClassMark kind="generated" className="mt-1.5 text-ai" />
        <span>
          <span className="sr-only">FINN interpretation: </span>
          {b.text}
          <Marks ids={b.cites} num={num} go={go} />
        </span>
      </p>
    );
  if (b.kind === "gap" || b.kind === "note")
    return (
      <p className={`rounded-md border px-3 py-2 text-xs ${b.kind === "gap" ? "border-alert/40 text-alert" : "border-line text-ink-2"}`}>
        <span className="font-medium">{b.kind === "gap" ? "Evidence gap: " : "Note: "}</span>
        {b.text}
        <Marks ids={b.cites} num={num} go={go} />
      </p>
    );
  const mark = b.kind === "guidance" ? "guidance" : b.info === "reported" ? "reported" : "computed";
  return (
    <div className="space-y-1">
      <p className="flex gap-2 text-sm leading-relaxed text-ink">
        <ClassMark kind={mark} className={`mt-1.5 ${mark === "guidance" ? "text-guided" : "text-ink-2"}`} />
        <span>
          {b.text}
          <Marks ids={b.cites} num={num} go={go} />
          {b.verdict && <span className="ml-2 inline-block align-middle"><Verdict v={b.verdict} /></span>}
        </span>
      </p>
      {b.implication && <p className="pl-4 text-xs text-ink-2"><span className="text-2xs uppercase tracking-[0.06em] text-ink-3">Implication </span>{b.implication}</p>}
    </div>
  );
}

function Sources({ a, r, order, go }: { a: AskAnswer; r: Report; order: string[]; go: (c: string) => void }) {
  const docs = Object.fromEntries(r.documents.map((d) => [d.id, d]));
  return (
    <details className="rounded-md border border-line">
      <summary className="cursor-pointer px-3 py-2 text-xs text-ink-2">Sources ({order.length})</summary>
      <ol className="space-y-1 px-3 pb-3">
        {order.map((c, i) => {
          const p = a.passages[c];
          const f = p ? null : factOf(c);
          const d = docs[p?.doc_id ?? f?.doc_id ?? ""];
          const label = p
            ? `${DOC_KIND[p.doc_kind]}${p.period ? `, ${p.period}` : ""}, p. ${p.page}${p.speaker ? `, ${p.speaker.split(",")[0]}` : ""}`
            : `${f?.label ?? c}${f?.display && !f.quote ? `: ${f.display}` : ""}${d ? ` (${DOC_KIND[d.kind]}${d.period ? ` ${d.period}` : ""}, p. ${f?.page})` : f?.info_class === "computed" ? " (FINN computed)" : ""}`;
          return (
            <li key={c} className="flex gap-2 text-2xs">
              <span className="num w-6 shrink-0 text-ink-3">[{i + 1}]</span>
              <button type="button" onClick={() => go(c)} className="text-left text-ink-2 hover:text-brass hover:underline">
                <ClassMark kind={p ? (p.table ? "reported" : "assertion") : (f?.info_class ?? "reported")} className="mr-1.5 inline text-ink-3" />
                {label}
              </button>
            </li>
          );
        })}
      </ol>
    </details>
  );
}
