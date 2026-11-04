"use client";

// Types for the engine's feed (schema finn.push.v1) and a small client hook.

import { useCallback, useEffect, useState } from "react";
import type { Category, Tier } from "./types";

export interface FeedEvidence {
  kind: string;
  page?: number | null;
  text?: string | null;
  formula?: string | null;
}
export interface FeedFigure {
  value: number | null;
  evidence?: FeedEvidence | null;
}
export interface FeedResultsRow {
  key: "revenue" | "ebitda" | "pbt" | "pat";
  label: string;
  current: FeedFigure;
  prev_q: FeedFigure;
  prev_y: FeedFigure;
  qoq: number | null;
  yoy: number | null;
}
export interface FeedResults {
  status: "ok" | "needs_review" | "failed" | "unavailable";
  reason?: string | null;
  basis: string;
  unit_detected?: string | null;
  period_label?: string | null;
  column_order?: string | null;
  page?: number | null;
  rows: FeedResultsRow[];
  ebitda_formula?: string | null;
  margin?: { current: number | null; prev_q: number | null; prev_y: number | null } | null;
  checks: { check: string; ok: boolean; detail: string }[];
  extractor_version?: string | null;
}
export interface FeedSourceRef {
  source: "bse" | "nse";
  source_id: string;
  listing_url: string | null;
  attachment_url: string | null;
  fetched_at: string;
  raw_path: string | null;
  fixture: boolean;
}
export interface FeedAnnouncement {
  id: string;
  symbol: string;
  company_on_filing: string;
  subject: string;
  headline: string | null;
  exchange_category: string | null;
  exchange_subcategory: string | null;
  filed_at: string;
  source: FeedSourceRef;
  attachment_size: number | null;
  duplicate_of: string | null;
  duplicates: string[];
  duplicate_reason: string | null;
  supersedes: string | null;
}
export interface FeedComponent {
  code: string;
  label: string;
  points: number;
  detail: string;
  inputs: Record<string, unknown>;
}
export interface FeedSignal {
  symbol: string;
  date: string;
  close: number;
  prev_close: number | null;
  ret_1d: number | null;
  avg_vol_20d: number | null;
  vol_ratio_20d: number | null;
  ret_stdev_60d: number | null;
  ret_z: number | null;
  split_or_bonus_on_date: boolean;
  bars_used: number;
  note: string | null;
}
export interface FeedEvent {
  id: string;
  symbol: string;
  category: Category;
  subtype: string | null;
  routine: boolean;
  title: string;
  first_filed_at: string;
  last_filed_at: string;
  announcements: FeedAnnouncement[];
  classification: { category: string; subtype: string | null; routine: boolean; method: string; rule_id: string | null; matched: string | null; confidence: string };
  facts: Record<string, unknown>;
  results: FeedResults | null;
  reaction: FeedSignal | null;
  reaction_session: string | null;
  materiality: { score: number; tier: Tier; raw_total: number; components: FeedComponent[]; floor: string | null; version: string };
  explanation: { what: string; why: string; generator: string; grounded: boolean; rejected_llm_reason: string | null };
  attachment: { status: string; url: string | null; note: string | null; announcement_id: string } | null;
  fixture: boolean;
}
export interface FeedCompany {
  symbol: string;
  name: string;
  sector: string | null;
  weight: number | null;
  is_financial: boolean;
  bse_code: string | null;
  eod: { available: boolean; bars: number; first: string | null; last: string | null };
  closes: { date: string; close: number; adj_close: number; volume: number | null }[];
}
export interface FeedMarket {
  symbol: string;
  signal: FeedSignal;
  explaining_event_ids: string[];
  window: [string, string];
}
export interface Feed {
  schema: "finn.push.v1";
  dataset: "live" | "fixture";
  dataset_note: string;
  generated_at: string;
  as_of: string;
  eod_date: string | null;
  versions: Record<string, string>;
  thresholds: { interrupt: number; brief: number };
  categories: { id: Category; label: string; description: string }[];
  sources: { source: string; ok: number; failed: number; rows: number; errors: string[] }[];
  unavailable: { symbol: string; source: string; error: string | null }[];
  rejections: string[];
  companies: FeedCompany[];
  market: FeedMarket[];
  events: FeedEvent[];
}

type State = { status: "loading" } | { status: "ready"; feed: Feed } | { status: "error"; code: string; message: string };

let cache: Feed | null = null;
let inflight: Promise<State> | null = null;

async function load(): Promise<State> {
  try {
    const r = await fetch("/api/v1/feed", { cache: "no-store" });
    const body = await r.json();
    if (!r.ok) return { status: "error", code: body?.error?.code ?? "ERROR", message: body?.error?.message ?? "The feed could not be loaded." };
    cache = body as Feed;
    return { status: "ready", feed: cache };
  } catch {
    return { status: "error", code: "NETWORK", message: "The feed could not be reached. Check that the app server is running." };
  }
}

export function useFeed() {
  const [state, setState] = useState<State>(cache ? { status: "ready", feed: cache } : { status: "loading" });
  const reload = useCallback(() => {
    cache = null;
    inflight = null;
    setState({ status: "loading" });
    load().then(setState);
  }, []);
  useEffect(() => {
    if (cache) return;
    inflight = inflight ?? load();
    let live = true;
    inflight.then((s) => live && setState(s));
    return () => {
      live = false;
    };
  }, []);
  return { ...state, reload } as State & { reload: () => void };
}

export function eventById(feed: Feed, id: string): FeedEvent | undefined {
  return feed.events.find((e) => e.id === id);
}

export function companyOf(feed: Feed, symbol: string): FeedCompany | undefined {
  return feed.companies.find((c) => c.symbol === symbol);
}
