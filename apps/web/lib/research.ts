"use client";

// Pull research reports (schema finn.research.v1) written by the engine
// (finn_engine.research), and the client hooks that read and request them.

import { useCallback, useEffect, useRef, useState } from "react";
import type { InfoClass } from "./types";
import { safeUrl } from "./safe-url";

export interface RFact {
  id: string;
  info_class: InfoClass;
  label: string;
  value?: number;
  unit?: "cr" | "pct" | "growth" | "pp" | "x" | "multiple" | "days";
  display?: string;
  period?: string;
  basis?: string;
  doc_id?: string;
  page?: number;
  section?: string;
  speaker?: string;
  role?: string;
  quote?: string;
  row_text?: string;
  column?: string;
  formula?: string;
  inputs?: string[];
  note?: string;
}

export interface RDoc {
  id: string;
  kind: "results" | "transcript" | "presentation" | "annual_report" | "press_release";
  title: string;
  period?: string | null;
  period_basis?: string | null;
  filed_at?: string | null;
  source: "bse" | "nse" | "company_ir" | "fixture";
  source_id?: string | null;
  url?: string | null;
  listing_url?: string | null;
  fetched_at?: string | null;
  raw_path?: string | null;
  sha256?: string | null;
  pages?: number | null;
  status: "parsed" | "unavailable" | "failed" | "not_used";
  status_reason?: string | null;
  fixture: boolean;
  parse: Record<string, unknown> & {
    attachment?: string | null;
    downloaded_from?: string;
    statements?: string[];
    basis?: Record<string, string>;
    unit?: string | null;
    checks?: { check: string; ok: boolean; detail: string }[];
    turns?: number;
    management_turns?: number;
    analyst_turns?: number;
    roster?: string[];
    call_date?: string;
    claims?: Record<string, number>;
    notes?: string[];
    complete?: boolean;
  };
}

export interface RTarget {
  kind: "range" | "point" | "floor" | "ceiling" | "delta" | "multiple" | "direction" | "words";
  low?: number | null;
  high?: number | null;
  unit?: string | null;
  text: string;
  reading: string;
}

export interface RClaim {
  id: string;
  kind: "guidance" | "assertion" | "outlook";
  metric?: string;
  metric_label?: string;
  segment?: string;
  quote: string;
  doc_id: string;
  doc_kind: RDoc["kind"];
  call_period?: string;
  page?: number;
  section?: string;
  speaker?: string;
  role: string;
  target?: RTarget;
  period?: string;
  hedge?: "firm" | "expected" | "aspirational" | "conditional";
  reaffirms?: boolean;
  withdraws?: boolean;
  theme?: string;
  tone: "positive" | "negative" | "neutral";
  explicit: boolean;
  fact_id?: string;
}

export interface RBand {
  kind: "range" | "point" | "floor" | "ceiling" | "delta" | "multiple";
  low?: number | null;
  high?: number | null;
  unit?: string | null;
}

export interface RHistory {
  call: string | null;
  doc_id: string;
  claim_id?: string | null;
  change: "first" | "also stated" | "differs" | "reiterated" | "raised" | "lowered" | "changed" | "withdrawn" | "not repeated" | "softened";
  target?: string | null;
  fact_id?: string | null;
  date?: string | null;
  band?: RBand | null;
}

export type RVerdict = "delivered" | "ahead" | "missed" | "pending" | "dropped" | "unverifiable" | "consistent" | "contradicted" | "partial";

export interface RLedger {
  id: string;
  kind: "guidance" | "assertion";
  metric: string;
  metric_label: string;
  segment?: string;
  period?: string;
  target?: string;
  reading?: string;
  hedge?: string;
  explicit: boolean;
  target_kind?: string;
  verdict: RVerdict;
  status_note?: string;
  detail: string;
  severity: number;
  actual_fact?: string;
  required_fact?: string;
  evidence: string[];
  history: RHistory[];
}

export interface RPoint {
  id: string;
  text: string;
  evidence: string[];
  rule: string;
  severity: number;
  implication?: string | null;
}

export interface RShift {
  id: string;
  theme: string;
  from_call: string | null;
  to_call: string | null;
  from_tone: string;
  to_tone: string;
  detail: string;
  evidence: string[];
}

export interface RGap {
  area: string;
  detail: string;
}

export interface RFetchLog {
  source: string;
  target: string;
  url?: string | null;
  ok: boolean;
  rows?: number;
  error?: string | null;
  fetched_at: string;
  raw_path?: string | null;
}

export interface CredRow {
  ledger: string;
  metric: string;
  period?: string;
  target?: string;
  first_target?: string | null;
  stated_on?: string | null;
  verdict: RVerdict;
  actual?: string | null;
  evidence: string[];
  [k: string]: unknown;
}

export interface CredIndicator {
  id: string;
  title: string;
  question: string;
  status: "observed" | "insufficient" | "none";
  n: number;
  headline: string;
  method: string;
  rows: CredRow[];
  stat?: Record<string, number | null> | null;
  years?: string[];
  by_family?: { family: string; kept: number; missed: number }[];
  repeated?: { metric: string; periods: string[] }[];
  met_only_after_revision?: string[];
  path?: { period: string; fact: string }[];
  management_said?: string[];
  contradictions?: string[];
}

export interface LaneStatement {
  ledger: string;
  period: string | null;
  period_end: string | null;
  date: string;
  until: string | null;
  change: RHistory["change"];
  target?: string | null;
  band?: RBand | null;
  fact?: string | null;
  call?: string | null;
  kind: "explicit" | "qualitative" | "silence";
}

export interface Lane {
  id: string;
  metric: string;
  label: string;
  unit: "pct" | "cr";
  better: "up" | "down";
  kind: string;
  checkable: boolean;
  reason?: string | null;
  statements: LaneStatement[];
  actuals: { period: string; date: string; fact: string; value: number; kind: string }[];
  outcomes: { ledger: string; period: string; date: string; verdict: RVerdict; status_note?: string; fact: string; value: number; closed: boolean; ytd?: string | null }[];
}

export interface Credibility {
  window: { calls: number; first_call: string | null; last_call: string | null; results: number; closed_years: string[] };
  rules: { min_closed: number; min_years: number; no_score: string };
  indicators: CredIndicator[];
  lanes: Lane[];
  interpretation: { id: string; rule: string; text: string; evidence: string[]; method: string; rules_text?: string }[];
  contradictions: RPoint[];
}

export interface RIdentity {
  symbol: string;
  name: string;
  isin?: string | null;
  series?: string | null;
  listed_on?: string | null;
  bse_code?: string | null;
  bse_name?: string | null;
  industry?: string | null;
  market_cap_cr?: number | null;
  is_financial: boolean;
  is_it_services: boolean;
  sources: string[];
  notes: string[];
}

type FactRef = string | null;

export interface Report {
  schema: "finn.research.v1";
  dataset: "live" | "fixture" | "files";
  dataset_note: string | null;
  generated_at: string;
  as_of: string;
  versions: Record<string, string>;
  identity: RIdentity;
  documents: RDoc[];
  counts: {
    documents: Record<string, number>;
    claims: Record<string, number>;
    claims_rejected_by_gates: number;
    verdicts: Record<string, number>;
  };
  facts: Record<string, RFact>;
  claims: RClaim[];
  ledger: RLedger[];
  sections: {
    business: { description: FactRef; industry?: string | null; segments: { name: string; share: number; fact: string; growth_fact: FactRef }[]; segment_period: string | null; gaps: RGap[] };
    snapshot: {
      period: string | null;
      basis?: string;
      rows: { key: string; label: string; value: FactRef; qoq: FactRef; yoy: FactRef }[];
      margins?: { label: string; value: FactRef; yoy_change: FactRef }[];
      ttm?: { label: string; value: FactRef }[];
      balance?: { label: string; value: FactRef }[];
      market?: { label: string; value: FactRef }[];
      gaps: RGap[];
    };
    trajectory: {
      quarters: string[];
      series: Record<string, FactRef[]>;
      annual: { period: string; revenue: FactRef; pat: FactRef; ebitda: FactRef; ebitda_margin: FactRef; revenue_growth: FactRef }[];
      restated: { period: string; field: string; earlier: number; later: number; earlier_doc: string; later_doc: string }[];
      gaps: RGap[];
    };
    balance_sheet: { dates: string[]; basis?: string; rows: { label: string; values: FactRef[] }[]; checks?: { check: string; ok: boolean; detail: string }[]; gaps: RGap[] };
    cash_quality: { periods: string[]; rows: { label: string; values: FactRef[] }[]; flags: { tone: "bull" | "bear"; text: string; evidence: string[] }[]; note?: string | null; gaps: RGap[] };
    nvn: { entries: string[]; shifts: RShift[]; discrepancies: RPoint[]; calls: { doc_id: string; period: string | null; complete: boolean }[] };
    guidance: { entries: string[]; commentary: { theme: string; facts: string[] }[] };
    bull_bear: { bull: RPoint[]; bear: RPoint[]; note: string };
  };
  credibility?: Credibility;
  audit: { reported: number; quotes: number; computed: number; market: number; points: number; ok: boolean };
  restatements: unknown[];
  checks: { check: string; ok: boolean; detail: string; doc?: string }[];
  gaps: RGap[];
  rejections: string[];
  fetch_log: RFetchLog[];
}

export interface Security {
  symbol: string;
  name: string;
  isin: string;
  series: string;
  fixture: boolean;
  list?: string;
}

export interface IndexEntry {
  symbol: string;
  name: string;
  industry?: string | null;
  dataset: string;
  as_of: string;
  generated_at: string;
  documents: Record<string, number>;
  flags: number;
}

export interface Job {
  symbol: string;
  status: "queued" | "running" | "done" | "error";
  stage: string | null;
  started_at: string;
  finished_at: string | null;
  error: null | { code: string; message: string; identity?: RIdentity; fetch_log?: RFetchLog[] };
}

export const STAGES: [string, string][] = [
  ["resolve", "Check the ticker against NSE's equity list"],
  ["discover", "Find results, transcripts, presentations and the annual report on BSE and NSE"],
  ["download", "Download the documents"],
  ["numbers", "Read the statements: P&L, balance sheet, cash flow, segments"],
  ["narrative", "Read transcripts and presentations: guidance and commentary"],
  ["ledger", "Compare what was said with what was reported"],
  ["sections", "Build the eight sections"],
];

// ------------------------------------------------------------------ evidence registry
// The global source sheet resolves fact ids against the report on screen.

let current: Report | null = null;
const listeners = new Set<() => void>();

export function setCurrentReport(r: Report | null) {
  current = r;
  listeners.forEach((l) => l());
}

export function currentReport(): Report | null {
  return current;
}

export function factOf(id: string | null | undefined): RFact | undefined {
  return id && current ? current.facts[id] : undefined;
}

export function docOf(id: string | null | undefined): RDoc | undefined {
  return id && current ? current.documents.find((d) => d.id === id) : undefined;
}

export const DOC_KIND: Record<RDoc["kind"], string> = {
  results: "Results filing",
  transcript: "Earnings-call transcript",
  presentation: "Investor presentation",
  annual_report: "Annual report",
  press_release: "Press release",
};

export function docLabel(d: RDoc): string {
  return `${DOC_KIND[d.kind]}${d.period ? `, ${d.period}` : ""}`;
}

/** Link to the filing at the cited page, when the document is a real filing with a URL. */
export function docHref(d: RDoc | undefined, page?: number | null): string | null {
  const u = d && !d.fixture ? safeUrl(d.url) : null;
  if (!u) return null;
  return page ? `${u}#page=${page}` : u;
}

// ------------------------------------------------------------------ hooks

export type ReportState =
  | { status: "loading" }
  | { status: "ready"; report: Report; engine: boolean }
  | { status: "none"; engine: boolean; job: Job | null; message?: string }
  | { status: "error"; message: string };

async function json(url: string, init?: RequestInit) {
  const r = await fetch(url, { cache: "no-store", ...init });
  let body: unknown = null;
  try {
    body = await r.json();
  } catch {
    /* empty body */
  }
  return { ok: r.ok, status: r.status, body: body as Record<string, unknown> | null };
}

export function useReport(symbol: string) {
  const [state, setState] = useState<ReportState>({ status: "loading" });
  const load = useCallback(async () => {
    const r = await json(`/api/v1/research/${encodeURIComponent(symbol)}`);
    if (r.ok && r.body && (r.body as { schema?: string }).schema === "finn.research.v1") {
      setCurrentReport(r.body as unknown as Report); // before render, so every figure resolves on first paint
      setState({ status: "ready", report: r.body as unknown as Report, engine: r.status === 200 && Boolean((r.body as { _engine?: boolean })._engine) });
    } else if (r.status === 404) {
      const b = (r.body ?? {}) as { engine?: boolean; job?: Job | null; error?: { message?: string } | string; message?: string };
      setState({ status: "none", engine: Boolean(b.engine), job: b.job ?? null, message: typeof b.error === "object" ? b.error?.message : b.message });
    } else {
      const b = (r.body ?? {}) as { error?: { message?: string } };
      setState({ status: "error", message: b.error?.message ?? `The research API returned ${r.status}.` });
    }
  }, [symbol]);
  useEffect(() => {
    setState({ status: "loading" });
    void load();
  }, [load]);
  useEffect(() => () => setCurrentReport(null), [symbol]);
  return { state, reload: load };
}

/** Starts (or joins) a research job and polls it until it ends. */
export function useJob(symbol: string, onDone: () => void) {
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const poll = useCallback(async () => {
    const r = await json(`/api/v1/research/${encodeURIComponent(symbol)}/job`);
    if (!r.ok || !r.body) {
      setError("Lost track of the research job.");
      return;
    }
    const j = r.body as unknown as Job;
    setJob(j);
    if (j.status === "done") onDone();
    else if (j.status !== "error") timer.current = setTimeout(poll, 900);
  }, [symbol, onDone]);
  const start = useCallback(async () => {
    setError(null);
    const r = await json(`/api/v1/research/${encodeURIComponent(symbol)}`, { method: "POST" });
    if (r.status === 202 && r.body) {
      setJob(r.body as unknown as Job);
      timer.current = setTimeout(poll, 600);
    } else {
      const b = (r.body ?? {}) as { error?: { message?: string } };
      setError(b.error?.message ?? `Couldn't start research (${r.status}).`);
    }
  }, [symbol, poll]);
  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);
  return { job, error, start };
}

export function useSecurities(q: string) {
  const [rows, setRows] = useState<Security[]>([]);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const s = q.trim();
    if (!s) {
      setRows([]);
      return;
    }
    setBusy(true);
    const ctl = new AbortController();
    const t = setTimeout(async () => {
      try {
        const r = await fetch(`/api/v1/securities?q=${encodeURIComponent(s)}`, { signal: ctl.signal, cache: "no-store" });
        const b = (await r.json()) as { results?: Security[] };
        setRows(b.results ?? []);
      } catch {
        /* aborted or offline: keep the previous list */
      } finally {
        setBusy(false);
      }
    }, 120);
    return () => {
      ctl.abort();
      clearTimeout(t);
    };
  }, [q]);
  return { rows, busy };
}

export function useIndex() {
  const [idx, setIdx] = useState<IndexEntry[] | null>(null);
  useEffect(() => {
    void json("/api/v1/research").then((r) => setIdx(((r.body as { companies?: IndexEntry[] } | null)?.companies ?? []) as IndexEntry[]));
  }, []);
  return idx;
}


// ------------------------------------------------------------------ Ask FINN

export interface Passage {
  id: string;
  doc_id: string;
  doc_kind: RDoc["kind"];
  period?: string | null;
  page: number;
  text: string;
  section?: string;
  speaker?: string;
  role?: string;
  question?: string;
  table?: boolean;
  score?: number;
}

export interface AskBlock {
  kind: "fact" | "guidance" | "management" | "finding" | "interpretation" | "table" | "note" | "gap";
  text: string;
  cites: string[];
  info?: string | null;
  verdict?: RVerdict;
  explicit?: boolean;
  rule?: string;
  implication?: string | null;
}

export interface AskAnswer {
  question: string;
  symbol: string;
  dataset: string;
  as_of: string;
  intent: string;
  topics?: string[];
  status: "answered" | "partial" | "insufficient" | "out_of_scope";
  blocks: AskBlock[];
  passages: Record<string, Passage>;
  documents?: string[];
  notes?: string[];
  method: string;
  model_rejected?: string;
}

export async function askFinn(symbol: string, question: string): Promise<{ ok: true; answer: AskAnswer } | { ok: false; message: string }> {
  try {
    const r = await fetch(`/api/v1/ask/${encodeURIComponent(symbol)}`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ question }), cache: "no-store" });
    const b = await r.json();
    if (r.ok) return { ok: true, answer: b as AskAnswer };
    return { ok: false, message: b?.error?.message ?? b?.message ?? `Ask FINN returned ${r.status}.` };
  } catch {
    return { ok: false, message: "Couldn't reach Ask FINN." };
  }
}

// Source navigation: any component can open a document at a page or passage.
export type SourceTarget = { symbol: string; docId: string; page?: number; passageId?: string };
export function openSource(t: SourceTarget) {
  window.dispatchEvent(new CustomEvent<SourceTarget>("finn:open-source", { detail: t }));
}
