// C4. Alert threshold behaviour, run against the web app's own read-time logic (apps/web/lib/push.ts).
//   npx tsx alerts_eval.ts <feed.json> <label>
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { computeAlerts, placeEvent } from "../apps/web/lib/push";
import { defaultRules } from "../apps/web/lib/taxonomy";
import type { Feed, FeedMarket } from "../apps/web/lib/feed";

type Row = { area: string; group: string; name: string; passed: boolean; detail: string; severity: string; data: Record<string, unknown> };
const checks: Row[] = [];
const check = (name: string, passed: boolean, detail = "", severity = "critical") =>
  checks.push({ area: "C", group: "C4 alert thresholds", name, passed, detail: detail.slice(0, 500), severity, data: {} });

const feed: Feed = JSON.parse(readFileSync(process.argv[2], "utf8"));
const label = process.argv[3] ?? "baseline";
const R = () => structuredClone(defaultRules());
const marketAlerts = (f: Feed, r = R()) => computeAlerts(f, r).filter((a) => a.kind !== "event");
const syms = (xs: { symbol: string }[]) => [...new Set(xs.map((x) => x.symbol))].sort();

// 1. Defaults on the fixture feed: ±5% price, 2x volume.
const planted: Record<string, [number, number]> = { SARANG: [-0.042, 2.6], MERIDIAN: [0.068, 3.4], LOTUS: [-0.056, 1.9], QUANTA: [0.039, 1.7], KESTREL: [0.004, 1.1] };
const expectDefault = Object.entries(planted).filter(([, [r, v]]) => Math.abs(r) * 100 >= 5 || v >= 2).map(([s]) => s).sort();
const got = syms(marketAlerts(feed).filter((a) => a.symbol in planted));
check("defaults (±5%, 2x): SARANG, MERIDIAN, LOTUS alert; QUANTA, KESTREL don't", JSON.stringify(got) === JSON.stringify(expectDefault), `got ${got}, expected ${expectDefault}`);

// 2. Moving each threshold changes exactly the expected set.
for (const [pct, vol] of [[3, 2], [5, 3], [6, 10], [10, 1.5], [1, 1.2]] as const) {
  const r = R();
  r.priceMovePct = pct;
  r.volumeMultiple = vol;
  const want = Object.entries(planted).filter(([, [ret, v]]) => Math.abs(ret) * 100 >= pct || v >= vol).map(([s]) => s).sort();
  const g = syms(marketAlerts(feed, r).filter((a) => a.symbol in planted));
  check(`price ±${pct}% / volume ${vol}x`, JSON.stringify(g) === JSON.stringify(want), `got ${g}, expected ${want}`);
}

// 3. Boundaries: exactly at the threshold alerts; just below doesn't; kind labels match the trigger.
const base = feed.market[0];
const mk = (symbol: string, ret: number | null, vr: number | null, split = false): FeedMarket =>
  ({ ...structuredClone(base), symbol, explaining_event_ids: [], signal: { ...structuredClone(base.signal), symbol, ret_1d: ret, vol_ratio_20d: vr, split_or_bonus_on_date: split } }) as FeedMarket;
const synth: Feed = { ...feed, events: [], market: [mk("AT5", 0.05, 1.0), mk("BELOW5", 0.0494, 1.0), mk("NEG5", -0.05, 1.0), mk("AT2X", 0.0, 2.0), mk("BELOW2X", 0.0, 1.94),
  mk("BOTH", -0.07, 3.1), mk("SPLIT", -0.5, 1.0, true), mk("NULLS", null, null), mk("ROUND", 0.04996, 1.0)] };
const sa = marketAlerts(synth);
const by = (s: string) => sa.filter((a) => a.symbol === s);
check("exactly +5.0% alerts", by("AT5").length === 1 && by("AT5")[0].kind === "price", JSON.stringify(by("AT5").map((a) => a.kind)));
check("+4.94% (shown as +4.9%) does not alert", by("BELOW5").length === 0, JSON.stringify(by("BELOW5").map((a) => a.title)));
check("-5.0% alerts (either direction)", by("NEG5").length === 1, "");
check("exactly 2.0x volume alerts as a volume alert", by("AT2X").length === 1 && by("AT2X")[0].kind === "volume", JSON.stringify(by("AT2X").map((a) => a.kind)));
check("1.94x volume (shown as 1.9×) does not alert", by("BELOW2X").length === 0, "");
check("price and volume together give one combined alert", by("BOTH").length === 1 && by("BOTH")[0].kind === "price_volume", JSON.stringify(by("BOTH").map((a) => a.kind)));
check("a -50% print on a split day does not raise a price alert", by("SPLIT").length === 0, JSON.stringify(by("SPLIT").map((a) => a.title)));
check("missing price and volume: no alert, no crash", by("NULLS").length === 0, "");
const shown = by("ROUND");
check("a move that rounds to 5.0% on screen is not silently left out", shown.length === 1 || !/5\.0%/.test(((0.04996 * 100).toFixed(1)) + "%"),
  `ret 4.996% displays as ${(0.04996 * 100).toFixed(1)}% but alerts=${shown.length}`, "normal");

// 4. Muting and category rules.
{
  const r = R();
  r.muted = ["SARANG"];
  const a = computeAlerts(feed, r);
  check("muting SARANG removes its market alerts", !a.some((x) => x.symbol === "SARANG" && x.kind !== "event"), "");
  const ev = a.filter((x) => x.symbol === "SARANG" && x.kind === "event");
  check("muting is market-only, as the setting says: SARANG's rating-downgrade event alert remains", ev.length >= 1, `${ev.length} event alerts`, "normal");
}
{
  const r = R();
  const target = feed.events.find((e) => e.materiality.tier === "interrupt" && !e.materiality.floor);
  if (target) {
    r.categories[target.category] = "hide";
    const a = computeAlerts(feed, r).filter((x) => x.kind === "event" && x.eventId === target.id);
    check(`'hide' on ${target.category} removes a non-floored interrupt (${target.symbol})`, a.length === 0, "");
    r.categories[target.category] = "brief";
    check(`'brief' on ${target.category} demotes it to the brief`, placeEvent(target, r).tier === "brief", placeEvent(target, r).tier);
  }
  const floored = feed.events.find((e) => e.materiality.floor);
  if (floored) {
    const r2 = R();
    r2.categories[floored.category] = "hide";
    check(`hard floor wins over 'hide' (${floored.symbol} ${floored.category}): still alerts`, placeEvent(floored, r2).tier === "interrupt", placeEvent(floored, r2).tier, "normal");
  }
  const routine = feed.events.find((e) => e.materiality.tier === "routine");
  if (routine) {
    const r3 = R();
    r3.categories[routine.category] = "interrupt";
    check(`'alert' on ${routine.category} promotes a routine filing to an alert`, computeAlerts(feed, r3).some((x) => x.eventId === routine.id), "");
  }
}

// 5. Event alerts cover only the last 7 days of the feed.
{
  const old = structuredClone(feed.events.find((e) => e.materiality.tier === "interrupt")!);
  old.id = "old";
  old.last_filed_at = new Date(new Date(feed.as_of).getTime() - 8 * 864e5).toISOString();
  const f2: Feed = { ...feed, events: [old], market: [] };
  check("an interrupt filed 8 days ago is not an alert", computeAlerts(f2, R()).length === 0, "");
}

mkdirSync(new URL("./results/", import.meta.url), { recursive: true });
writeFileSync(new URL(`./results/alerts_${label}.json`, import.meta.url), JSON.stringify({ suite: "alerts", label, checks }, null, 1));
const fails = checks.filter((c) => !c.passed);
for (const c of checks) console.log(`${c.passed ? "PASS" : "FAIL"} ${c.name}${c.passed ? "" : "  | " + c.detail}`);
console.log(`${checks.length - fails.length}/${checks.length} alert checks passed`);
