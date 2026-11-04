// Read-time logic over the engine feed: apply the user's category rules (hard
// floors still win), build the windowed brief, and evaluate alerts against the
// user's thresholds. Scores and reasoning come from the engine unchanged.

import type { AlertItem, Category, CategoryRule, Rules, Tier } from "./types";
import type { Feed, FeedEvent } from "./feed";
import { multiple, pct } from "./format";
import { DEMO_LAST_LOOKED } from "./demo/companies";

export interface PlacedEvent {
  event: FeedEvent;
  tier: Tier;
  floorApplied: boolean;
  ruleApplied: boolean;
  at: string;
}

export function placeEvent(e: FeedEvent, rules: Rules): PlacedEvent {
  const rule: CategoryRule = rules.categories[e.category] ?? "default";
  const base = e.materiality.tier;
  let tier: Tier = base;
  if (rule === "interrupt") tier = "interrupt";
  else if (rule === "brief") tier = base === "interrupt" ? "brief" : base;
  else if (rule === "hide") tier = "routine";
  let floorApplied = false;
  if (e.materiality.floor && tier !== "interrupt") {
    tier = "interrupt";
    floorApplied = true;
  }
  return { event: e, tier, floorApplied, ruleApplied: tier !== base && !floorApplied, at: e.last_filed_at };
}

export type WindowKey = "since" | "24h" | "3d" | "7d";
const HOURS = { "24h": 24, "3d": 72, "7d": 168 } as const;

export function windowStart(key: WindowKey, lastLooked: string, feed: Feed): string {
  const asOf = new Date(feed.as_of).getTime();
  if (key !== "since") return new Date(asOf - HOURS[key] * 3600e3).toISOString();
  // A fresh device on live data: "since last look" means the last 24 hours.
  if (feed.dataset === "live" && lastLooked === DEMO_LAST_LOOKED) return new Date(asOf - 24 * 3600e3).toISOString();
  return lastLooked;
}

const ts = (iso: string) => new Date(iso).getTime();

export interface Brief {
  since: string;
  until: string;
  filings: number;
  duplicatesMerged: number;
  needsYou: PlacedEvent[];
  worthALook: PlacedEvent[];
  routine: { category: Category; items: PlacedEvent[] }[];
  setAside: PlacedEvent[];
}

export function buildBrief(feed: Feed, key: WindowKey, lastLooked: string, rules: Rules, triage: Record<string, "noted" | "snoozed">): Brief {
  const since = windowStart(key, lastLooked, feed);
  const until = feed.as_of;
  const inWindow = feed.events.map((e) => placeEvent(e, rules)).filter((p) => ts(p.at) > ts(since) && ts(p.at) <= ts(until));
  const active = inWindow.filter((p) => !triage[p.event.id]);
  const byScore = (a: PlacedEvent, b: PlacedEvent) => b.event.materiality.score - a.event.materiality.score;
  const groups = new Map<Category, PlacedEvent[]>();
  active.filter((p) => p.tier === "routine").forEach((p) => groups.set(p.event.category, [...(groups.get(p.event.category) ?? []), p]));
  const all = inWindow.flatMap((p) => p.event.announcements);
  return {
    since,
    until,
    filings: all.filter((a) => !a.duplicate_of).length,
    duplicatesMerged: all.filter((a) => a.duplicate_of).length,
    needsYou: active.filter((p) => p.tier === "interrupt").sort(byScore),
    worthALook: active.filter((p) => p.tier === "brief").sort(byScore),
    routine: [...groups.entries()]
      .map(([category, items]) => ({ category, items: items.sort((a, b) => ts(b.at) - ts(a.at)) }))
      .sort((a, b) => b.items.length - a.items.length),
    setAside: inWindow.filter((p) => triage[p.event.id]),
  };
}

/** Filing alerts: events placed at "interrupt" in the last 7 days. Market alerts: latest session vs thresholds. */
export function computeAlerts(feed: Feed, rules: Rules): AlertItem[] {
  const since = ts(feed.as_of) - 7 * 864e5;
  const events: AlertItem[] = feed.events
    .map((e) => placeEvent(e, rules))
    .filter((p) => p.tier === "interrupt" && ts(p.at) > since)
    .map((p) => ({
      key: `event:${p.event.id}`,
      kind: "event",
      symbol: p.event.symbol,
      at: p.at,
      title: p.event.title,
      detail: p.event.explanation.why,
      eventId: p.event.id,
      category: p.event.category,
    }));
  const byId = new Map(feed.events.map((e) => [e.id, e]));
  const market: AlertItem[] = [];
  for (const m of feed.market) {
    if (rules.muted.includes(m.symbol)) continue;
    const s = m.signal;
    // Compared at the precision shown on screen (0.1% and 0.1×), so a move displayed as "5.0%" meets a 5% threshold.
    const priceHit = s.ret_1d !== null && !s.split_or_bonus_on_date && Math.round(Math.abs(s.ret_1d) * 1000) / 10 >= rules.priceMovePct;
    const volHit = s.vol_ratio_20d !== null && Math.round(s.vol_ratio_20d * 10) / 10 >= rules.volumeMultiple;
    if (!priceHit && !volHit) continue;
    const explainers = m.explaining_event_ids.map((id) => byId.get(id)).filter(Boolean) as FeedEvent[];
    const kind = priceHit && volHit ? "price_volume" : priceHit ? "price" : "volume";
    const parts = [
      priceHit && s.ret_1d !== null ? `${pct(s.ret_1d)} on the day` : null,
      volHit && s.vol_ratio_20d !== null ? `volume ${multiple(s.vol_ratio_20d)} its 20-day average` : null,
    ].filter(Boolean);
    market.push({
      key: `${kind}:${m.symbol}:${s.date}`,
      kind,
      symbol: m.symbol,
      at: `${s.date}T16:30:00+05:30`,
      title: parts.join(", "),
      detail: explainers.length ? `Explained by a filing: ${explainers[0].title}` : "No filing explains this move",
      explained: explainers.length > 0,
      eventId: explainers[0]?.id,
      ret: s.ret_1d ?? undefined,
      volRatio: s.vol_ratio_20d ?? undefined,
      z: s.ret_z,
    });
  }
  return [...market, ...events].sort((a, b) => ts(b.at) - ts(a.at));
}
