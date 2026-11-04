"use client";

import Link from "next/link";
import { useState } from "react";
import type { Feed, FeedCompany } from "@/lib/feed";
import { companyOf } from "@/lib/feed";
import { dateTimeIST, multiple, pct, rupees, signClass } from "@/lib/format";
import { useStore } from "@/lib/store";
import { useWidth } from "../research/useWidth";
import { DatasetBadge, FeedGate } from "./FeedGate";
import { SectionHead } from "../ui/primitives";

export function MoveDetailScreen({ symbol }: { symbol: string }) {
  return (
    <FeedGate>
      {(feed) => {
        const c = companyOf(feed, symbol);
        return c ? <MoveDetail feed={feed} c={c} /> : <p className="text-sm text-ink-2">{symbol} isn&apos;t in the current feed&apos;s portfolio.</p>;
      }}
    </FeedGate>
  );
}

function MoveDetail({ feed, c }: { feed: Feed; c: FeedCompany }) {
  const { rules } = useStore();
  const m = feed.market.find((x) => x.symbol === c.symbol);
  const s = m?.signal;
  const explainers = (m?.explaining_event_ids ?? []).map((id) => feed.events.find((e) => e.id === id)).filter(Boolean);
  const priceHit = s && s.ret_1d !== null && !s.split_or_bonus_on_date && Math.abs(s.ret_1d) * 100 >= rules.priceMovePct;
  const volHit = s && s.vol_ratio_20d !== null && s.vol_ratio_20d >= rules.volumeMultiple;
  const last = c.closes[c.closes.length - 1];

  return (
    <div className="space-y-8">
      <header className="space-y-2">
        <Link href="/alerts" className="text-xs text-ink-3 hover:text-ink-2">‹ Alerts</Link>
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-xl font-semibold">{c.symbol}</h1>
          {feed.dataset === "fixture" && <DatasetBadge dataset="fixture" />}
        </div>
        <p className="text-sm text-ink-2">{c.name}. End-of-day move{s ? `, session of ${s.date}` : ""}.</p>
      </header>

      {!s ? (
        <p className="rounded-md border border-line bg-surface px-3 py-3 text-sm text-ink-2">No end-of-day prices for {c.symbol} on the last run, so no move can be computed.</p>
      ) : (
        <>
          <section aria-labelledby="sig" className="space-y-3">
            <SectionHead id="sig" title="The move" />
            <dl className="num grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-4">
              <Stat t="Close" v={`₹${rupees(s.close)}`} />
              <Stat t="Day move (adjusted)" v={<span className={signClass(s.ret_1d)}>{pct(s.ret_1d)}</span>} />
              <Stat t="Volume vs 20-day avg" v={s.vol_ratio_20d !== null ? multiple(s.vol_ratio_20d) : "n/a"} />
              <Stat t="Move vs own volatility" v={s.ret_z !== null ? `${s.ret_z >= 0 ? "+" : ""}${s.ret_z.toFixed(1)} sd` : "n/a"} />
            </dl>
            <dl className="num grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-xs">
              <dt className="text-ink-3">Previous close</dt><dd className="text-ink-2">{s.prev_close !== null ? `₹${rupees(s.prev_close)}` : "n/a"}</dd>
              <dt className="text-ink-3">Session volume</dt><dd className="text-ink-2">{last?.volume?.toLocaleString("en-IN") ?? "n/a"}</dd>
              <dt className="text-ink-3">20-day average volume</dt><dd className="text-ink-2">{s.avg_vol_20d !== null ? Math.round(s.avg_vol_20d).toLocaleString("en-IN") : "n/a"} (previous 20 sessions, this one excluded)</dd>
              <dt className="text-ink-3">60-day return st. dev.</dt><dd className="text-ink-2">{s.ret_stdev_60d !== null ? pct(s.ret_stdev_60d, 2, false) : "n/a"}</dd>
              <dt className="text-ink-3">Split or bonus that day</dt><dd className="text-ink-2">{s.split_or_bonus_on_date ? "Yes: price alert suppressed" : "No"}</dd>
              <dt className="text-ink-3">Sessions of history</dt><dd className="text-ink-2">{s.bars_used}{s.note ? `. ${s.note}` : ""}</dd>
            </dl>
          </section>

          <section aria-labelledby="thr" className="space-y-2">
            <SectionHead id="thr" title="Against your thresholds" action={<Link href="/alerts?tab=rules" className="inline-flex min-h-6 items-center text-xs text-brass hover:underline">Change</Link>} />
            <ul className="space-y-1 text-sm">
              <li className={priceHit ? "text-alert" : "text-ink-2"}>Price ±{rules.priceMovePct}%: {priceHit ? "crossed" : s.split_or_bonus_on_date ? "not checked (split or bonus day)" : "not crossed"}</li>
              <li className={volHit ? "text-alert" : "text-ink-2"}>Volume {rules.volumeMultiple}× average: {volHit ? "crossed" : "not crossed"}</li>
            </ul>
          </section>

          <section aria-labelledby="why" className="space-y-2">
            <SectionHead id="why" title="Filings that could explain it" count={explainers.length} />
            <p className="num text-xs text-ink-3">Window: {m && dateTimeIST(m.window[0])} to {m && dateTimeIST(m.window[1])} (previous close to this close).</p>
            {explainers.length ? (
              <ul className="space-y-1.5">
                {explainers.map((e) => e && (
                  <li key={e.id}><Link href={`/events/${e.id}`} className="-my-1 inline-block py-1 text-sm text-ink hover:text-brass">{e.explanation.what}</Link></li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-alert">No filing explains this move. The information behind it is somewhere you haven&apos;t seen.</p>
            )}
          </section>
        </>
      )}

      {c.closes.length > 1 && (
        <section aria-labelledby="ch" className="space-y-2">
          <SectionHead id="ch" title="Last sessions" count={`${c.closes.length} sessions`} />
          <PriceVolume closes={c.closes} />
          <p className="text-2xs text-ink-3">
            End-of-day bars {c.eod.first} to {c.eod.last} ({c.eod.bars} sessions{feed.dataset === "fixture" ? ", synthetic fixture prices" : ""}). Price line uses adjusted closes.
          </p>
        </section>
      )}
    </div>
  );
}

function Stat({ t, v }: { t: string; v: React.ReactNode }) {
  return (
    <div className="bg-base px-3 py-2.5">
      <dt className="text-2xs text-ink-3">{t}</dt>
      <dd className="mt-0.5 text-md font-medium">{v}</dd>
    </div>
  );
}

function PriceVolume({ closes }: { closes: FeedCompany["closes"] }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const n = closes.length;
  const padL = 48;
  const padR = 8;
  const w = Math.max(200, width - padL - padR);
  const x = (i: number) => padL + (i / (n - 1)) * w;
  const ps = closes.map((c) => c.adj_close);
  const lo = Math.min(...ps);
  const hi = Math.max(...ps);
  const pH = 120;
  const py = (v: number) => 6 + (1 - (v - lo) / (hi - lo || 1)) * (pH - 12);
  const vs = closes.map((c) => c.volume ?? 0);
  const vMax = Math.max(...vs) || 1;
  const vH = 64;
  const bw = Math.max(1, (w / n) * 0.7);
  const line = ps.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${py(v).toFixed(1)}`).join("");
  const onMove = (ev: React.PointerEvent<SVGRectElement>) => {
    const r = ev.currentTarget.getBoundingClientRect();
    setHover(Math.max(0, Math.min(n - 1, Math.round(((ev.clientX - r.left) / r.width) * (n - 1)))));
  };
  const h = hover !== null ? closes[hover] : null;
  return (
    <div ref={ref} className="relative" onPointerLeave={() => setHover(null)}>
      {h && (
        <div className="pointer-events-none absolute right-0 top-0 rounded-md border border-line-strong bg-raised px-2.5 py-1.5 text-xs">
          <p className="font-medium">{h.date}</p>
          <p className="num text-ink-2">Close ₹{rupees(h.close)}</p>
          <p className="num text-ink-2">Volume {(h.volume ?? 0).toLocaleString("en-IN")}</p>
        </div>
      )}
      <p className="text-xs text-ink-2">Adjusted close, ₹</p>
      <svg width={width} height={pH} role="img" aria-label="Adjusted closing prices" className="block">
        {[lo, (lo + hi) / 2, hi].map((t) => (
          <g key={t}>
            <line x1={padL} x2={width - padR} y1={py(t)} y2={py(t)} stroke="var(--color-line)" />
            <text x={padL - 6} y={py(t) + 3.5} textAnchor="end" fontSize="10.5" fill="var(--color-ink-3)">{Math.round(t).toLocaleString("en-IN")}</text>
          </g>
        ))}
        <path d={line} fill="none" stroke="var(--color-ink)" strokeWidth="1.5" />
        {hover !== null && <line x1={x(hover)} x2={x(hover)} y1={0} y2={pH} stroke="var(--color-line-strong)" />}
        <circle cx={x(n - 1)} cy={py(ps[n - 1])} r="3" fill="var(--color-ink)" stroke="var(--color-base)" strokeWidth="2" />
        <rect x={padL} y={0} width={w} height={pH} fill="transparent" onPointerMove={onMove} onPointerDown={onMove} />
      </svg>
      <p className="mt-2 text-xs text-ink-2">Volume</p>
      <svg width={width} height={vH + 16} role="img" aria-label="Daily volume" className="block">
        {vs.map((v, i) => (
          <rect key={i} x={x(i) - bw / 2} y={vH - (v / vMax) * (vH - 4)} width={bw} height={(v / vMax) * (vH - 4)} fill={i === n - 1 ? "var(--color-alert)" : i === hover ? "var(--color-ink-2)" : "var(--color-ink-3)"} opacity={i === n - 1 || i === hover ? 1 : 0.6} />
        ))}
        <text x={padL} y={vH + 13} fontSize="10.5" fill="var(--color-ink-3)">{closes[0].date}</text>
        <text x={width - padR} y={vH + 13} textAnchor="end" fontSize="10.5" fill="var(--color-ink-3)">{closes[n - 1].date}</text>
        <rect x={padL} y={0} width={w} height={vH} fill="transparent" onPointerMove={onMove} onPointerDown={onMove} />
      </svg>
    </div>
  );
}
