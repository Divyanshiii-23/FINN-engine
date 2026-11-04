"use client";

import { useEffect, useMemo, useState } from "react";
import { useStore } from "@/lib/store";
import type { Feed } from "@/lib/feed";
import { computeAlerts, placeEvent } from "@/lib/push";
import { CATEGORY_LABEL, CATEGORY_ORDER, FLOOR_NOTE, defaultRules } from "@/lib/taxonomy";
import type { Category, CategoryRule, Rules } from "@/lib/types";
import { dateTimeIST } from "@/lib/format";
import { AlertRow } from "./AlertRow";
import { DatasetBadge, FeedGate } from "../push/FeedGate";
import { SectionHead, Segmented, Stepper, Switch, TextButton } from "../ui/primitives";
import { queryParam } from "@/lib/query";

type Tab = "inbox" | "rules" | "sources";

export function AlertsScreen() {
  return <FeedGate>{(feed) => <Alerts feed={feed} />}</FeedGate>;
}

function Alerts({ feed }: { feed: Feed }) {
  const { rules, setRules, read, markRead } = useStore();
  const [tab, setTab] = useState<Tab>("inbox");
  useEffect(() => {
    const t = queryParam("tab");
    if (t === "rules" || t === "sources") setTab(t);
  }, []);
  const switchTab = (t: Tab) => {
    setTab(t);
    window.history.replaceState(null, "", t === "inbox" ? "/alerts" : `/alerts?tab=${t}`);
  };
  const alerts = useMemo(() => computeAlerts(feed, rules), [feed, rules]);
  const unread = alerts.filter((a) => !read.includes(a.key)).length;
  const failing = feed.sources.reduce((n, s) => n + s.failed, 0);

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-lg font-semibold">Alerts</h1>
        <Segmented
          label="Alerts view"
          value={tab}
          onChange={switchTab}
          options={[
            { value: "inbox", label: `Inbox${unread ? ` ${unread}` : ""}` },
            { value: "rules", label: "Rules" },
            { value: "sources", label: `Sources${failing ? ` (${failing} failed)` : ""}` },
          ]}
        />
      </header>
      {tab === "inbox" && <Inbox feed={feed} alerts={alerts} onMarkAll={(keys) => markRead(keys)} onEditRules={() => switchTab("rules")} />}
      {tab === "rules" && <RulesEditor feed={feed} rules={rules} setRules={setRules} />}
      {tab === "sources" && <Sources feed={feed} />}
    </div>
  );
}

type Kind = "all" | "filings" | "market" | "unexplained";

function Inbox({ feed, alerts, onMarkAll, onEditRules }: { feed: Feed; alerts: ReturnType<typeof computeAlerts>; onMarkAll: (keys: string[]) => void; onEditRules: () => void }) {
  const { read } = useStore();
  const [kind, setKind] = useState<Kind>("all");
  const [category, setCategory] = useState<string>("");
  const [symbol, setSymbol] = useState<string>("");
  const [unreadOnly, setUnreadOnly] = useState(false);

  const shown = alerts.filter(
    (a) =>
      (kind === "all" || (kind === "filings" ? a.kind === "event" : kind === "market" ? a.kind !== "event" : a.kind !== "event" && !a.explained)) &&
      (!category || a.category === category) &&
      (!symbol || a.symbol === symbol) &&
      (!unreadOnly || !read.includes(a.key)),
  );
  const unreadShown = shown.filter((a) => !read.includes(a.key));
  const cats = [...new Set(alerts.map((a) => a.category).filter(Boolean))] as Category[];
  const syms = [...new Set(alerts.map((a) => a.symbol))].sort();
  const filtered = kind !== "all" || category || symbol || unreadOnly;
  const select = "h-8 rounded-md border border-line bg-surface px-2 text-xs text-ink focus:border-brass focus:outline-none";

  return (
    <div className="space-y-5">
      <div className="space-y-3">
        <div className="-mx-4 overflow-x-auto px-4 no-scrollbar sm:mx-0 sm:px-0">
          <Segmented
            label="Alert type"
            value={kind}
            onChange={setKind}
            options={[
              { value: "all", label: "All" },
              { value: "filings", label: "Filings" },
              { value: "market", label: "Market moves" },
              { value: "unexplained", label: "Unexplained moves" },
            ]}
          />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="sr-only" htmlFor="f-cat">Category</label>
          <select id="f-cat" className={select} value={category} onChange={(e) => setCategory(e.target.value)} disabled={kind === "market" || kind === "unexplained"}>
            <option value="">All categories</option>
            {cats.map((c) => <option key={c} value={c}>{CATEGORY_LABEL[c]}</option>)}
          </select>
          <label className="sr-only" htmlFor="f-sym">Company</label>
          <select id="f-sym" className={select} value={symbol} onChange={(e) => setSymbol(e.target.value)}>
            <option value="">All companies</option>
            {syms.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <span className="flex items-center gap-2 text-xs text-ink-2">
            <Switch checked={unreadOnly} onChange={setUnreadOnly} label="Unread only" /> Unread only
          </span>
          {filtered && (
            <TextButton onClick={() => { setKind("all"); setCategory(""); setSymbol(""); setUnreadOnly(false); }}>Clear filters</TextButton>
          )}
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-ink-2">
          <p className="num">
            {shown.length} of {alerts.length} alerts{unreadShown.length ? `, ${unreadShown.length} unread` : ""}. Filings from the last 7 days, market moves from the session of {feed.eod_date ?? "n/a"}.
          </p>
          <div className="-mr-2 flex gap-1">
            {unreadShown.length > 0 && <TextButton onClick={() => onMarkAll(unreadShown.map((a) => a.key))}>Mark shown as read</TextButton>}
            <TextButton tone="accent" onClick={onEditRules}>Edit rules</TextButton>
          </div>
        </div>
      </div>
      <section aria-label="Alerts">
        {shown.length ? shown.map((a) => <AlertRow key={a.key} a={a} feed={feed} />) : <p className="border-t border-line py-4 text-sm text-ink-3">No alerts match these filters.</p>}
      </section>
    </div>
  );
}

const RULE_OPTIONS: { value: CategoryRule; label: string }[] = [
  { value: "default", label: "Auto" },
  { value: "interrupt", label: "Alert" },
  { value: "brief", label: "Brief" },
  { value: "hide", label: "Hide" },
];

function RulesEditor({ feed, rules, setRules }: { feed: Feed; rules: Rules; setRules: (r: Rules) => void }) {
  const market = useMemo(() => computeAlerts(feed, rules).filter((a) => a.kind !== "event"), [feed, rules]);
  const since = new Date(feed.as_of).getTime() - 7 * 864e5;
  const counts = useMemo(() => {
    const m = new Map<Category, { total: number; alerting: number }>();
    feed.events.forEach((e) => {
      const p = placeEvent(e, rules);
      if (new Date(p.at).getTime() <= since) return;
      const cur = m.get(e.category) ?? { total: 0, alerting: 0 };
      m.set(e.category, { total: cur.total + 1, alerting: cur.alerting + (p.tier === "interrupt" ? 1 : 0) });
    });
    return m;
  }, [feed, rules, since]);
  const set = (patch: Partial<Rules>) => setRules({ ...rules, ...patch });
  const setCat = (c: Category, v: CategoryRule) => set({ categories: { ...rules.categories, [c]: v } });
  const toggleMute = (sym: string, on: boolean) => set({ muted: on ? rules.muted.filter((s) => s !== sym) : [...rules.muted, sym] });

  return (
    <div className="space-y-10">
      <p className="max-w-[64ch] text-xs text-ink-2">Rules are saved on this device and apply straight away to the brief, the inbox and the portfolio. They change where items appear, not the engine&apos;s scores.</p>
      <section aria-labelledby="r-market" className="space-y-4">
        <SectionHead id="r-market" title="Market moves" />
        <p className="text-xs text-ink-3">Checked against end-of-day prices. Price moves use adjusted closes; split and bonus days are never flagged.</p>
        <Stepper label="Price move in a day" hint="Alert when a holding moves at least this much either way" value={rules.priceMovePct} onChange={(v) => set({ priceMovePct: v })} min={1} max={20} step={0.5} prefix="±" suffix="%" />
        <Stepper label="Volume against 20-day average" hint="Today's volume over the mean of the previous 20 sessions" value={rules.volumeMultiple} onChange={(v) => set({ volumeMultiple: v })} min={1.2} max={10} step={0.1} suffix="×" />
        <p className="num rounded-md border border-line bg-surface px-3 py-2 text-xs text-ink-2">
          In the session of {feed.eod_date ?? "n/a"} these thresholds flag{" "}
          <span className="text-ink">{market.length ? `${market.length} ${market.length === 1 ? "holding" : "holdings"}: ${market.map((a) => a.symbol).join(", ")}` : "no holdings"}</span>.
        </p>
      </section>
      <section aria-labelledby="r-cat" className="space-y-3">
        <SectionHead id="r-cat" title="Filing types" />
        <dl className="grid gap-x-4 gap-y-1 text-xs text-ink-3 sm:grid-cols-2">
          <div><dt className="inline text-ink-2">Auto: </dt><dd className="inline">use FINN&apos;s score.</dd></div>
          <div><dt className="inline text-ink-2">Alert: </dt><dd className="inline">always interrupt and add to the inbox.</dd></div>
          <div><dt className="inline text-ink-2">Brief: </dt><dd className="inline">show in the brief, never interrupt.</dd></div>
          <div><dt className="inline text-ink-2">Hide: </dt><dd className="inline">collapse with routine paperwork.</dd></div>
        </dl>
        <ul>
          {CATEGORY_ORDER.map((c) => {
            const n = counts.get(c);
            return (
              <li key={c} className="flex flex-col gap-2 border-b border-line py-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0">
                  <p className="text-sm text-ink">{CATEGORY_LABEL[c]}</p>
                  <p className="num text-2xs text-ink-3">
                    {n ? `${n.total} in 7 days, ${n.alerting} alerting` : "None in 7 days"}
                    {FLOOR_NOTE[c] && <span>. {FLOOR_NOTE[c]}</span>}
                  </p>
                </div>
                <Segmented size="sm" label={`Rule for ${CATEGORY_LABEL[c]}`} value={rules.categories[c]} onChange={(v) => setCat(c, v)} options={RULE_OPTIONS} />
              </li>
            );
          })}
        </ul>
      </section>
      <section aria-labelledby="r-mute" className="space-y-3">
        <SectionHead id="r-mute" title="Market alerts by holding" count={`${feed.companies.length - rules.muted.filter((m) => feed.companies.some((c) => c.symbol === m)).length} on`} />
        <ul className="grid sm:grid-cols-2 sm:gap-x-8">
          {feed.companies.map((h) => {
            const on = !rules.muted.includes(h.symbol);
            return (
              <li key={h.symbol} className="flex items-center justify-between gap-3 border-b border-line py-2.5">
                <span className="min-w-0 truncate text-sm">
                  <span className="font-semibold tracking-[0.02em]">{h.symbol}</span>
                  <span className="text-ink-3"> {h.name}</span>
                  {!h.eod.available && <span className="text-2xs text-alert"> no price data</span>}
                </span>
                <Switch checked={on} onChange={(v) => toggleMute(h.symbol, v)} label={`Market alerts for ${h.symbol}`} />
              </li>
            );
          })}
        </ul>
      </section>
      <div className="border-t border-line pt-4">
        <TextButton onClick={() => setRules(defaultRules())}>Reset rules to defaults</TextButton>
      </div>
    </div>
  );
}

function Sources({ feed }: { feed: Feed }) {
  return (
    <div className="space-y-8">
      <section className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <DatasetBadge dataset={feed.dataset} />
          <span className="num text-xs text-ink-3">Generated {dateTimeIST(feed.generated_at)}. Prices to {feed.eod_date ?? "n/a"}.</span>
        </div>
        <p className="max-w-[70ch] text-sm text-ink-2">{feed.dataset_note}</p>
      </section>
      <section aria-labelledby="s-health" className="space-y-2">
        <SectionHead id="s-health" title="Last run, by source" />
        <table className="w-full table-fixed text-sm">
          <thead>
            <tr className="border-b border-line text-2xs text-ink-3">
              <th scope="col" className="py-1.5 text-left font-normal">Source</th>
              <th scope="col" className="w-12 py-1.5 pl-2 text-right font-normal">OK</th>
              <th scope="col" className="w-14 py-1.5 pl-2 text-right font-normal">Failed</th>
              <th scope="col" className="w-16 py-1.5 pl-2 text-right font-normal">Rows</th>
            </tr>
          </thead>
          <tbody>
            {feed.sources.map((s) => (
              <tr key={s.source} className="border-b border-line/60 align-top">
                <th scope="row" className="py-1.5 text-left font-normal">
                  {s.source.toUpperCase()}
                  {s.errors.length > 0 && (
                    <ul className="mt-1 space-y-0.5 text-2xs text-ink-3">
                      {s.errors.map((e) => <li key={e}>{e}</li>)}
                    </ul>
                  )}
                </th>
                <td className="num py-1.5 pl-2 text-right">{s.ok}</td>
                <td className={`num py-1.5 pl-2 text-right ${s.failed ? "text-alert" : ""}`}>{s.failed}</td>
                <td className="num py-1.5 pl-2 text-right">{s.rows.toLocaleString("en-IN")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <section aria-labelledby="s-rej" className="space-y-2">
        <SectionHead id="s-rej" title="Rows rejected" count={feed.rejections.length} />
        {feed.rejections.length ? (
          <ul className="space-y-1 text-xs text-ink-2">{feed.rejections.map((r) => <li key={r}>{r}</li>)}</ul>
        ) : (
          <p className="text-xs text-ink-3">None.</p>
        )}
      </section>
      <section aria-labelledby="s-ver" className="space-y-2">
        <SectionHead id="s-ver" title="Versions" />
        <dl className="num grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-xs">
          {Object.entries(feed.versions).map(([k, v]) => (
            <div key={k} className="contents"><dt className="text-ink-3">{k}</dt><dd className="text-ink-2">{v}</dd></div>
          ))}
        </dl>
      </section>
    </div>
  );
}
