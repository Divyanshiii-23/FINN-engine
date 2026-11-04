"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import type { Feed } from "@/lib/feed";
import { computeAlerts } from "@/lib/push";
import { useStore } from "@/lib/store";
import { multiple, pct, rupees, signClass } from "@/lib/format";
import { Sparkline } from "../ui/Sparkline";
import { ClassTag } from "../ui/primitives";
import { DatasetBadge, FeedGate } from "../push/FeedGate";

type SortKey = "weight" | "ret1d" | "volRatio" | "ret3m" | "symbol";

export function PortfolioScreen() {
  return <FeedGate>{(feed) => <Portfolio feed={feed} />}</FeedGate>;
}

function Portfolio({ feed }: { feed: Feed }) {
  const router = useRouter();
  const { rules, read } = useStore();
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: "weight", dir: -1 });

  const rows = useMemo(
    () =>
      feed.companies.map((c) => {
        const s = feed.market.find((m) => m.symbol === c.symbol)?.signal;
        const closes = c.closes.map((b) => b.adj_close);
        const back = closes.length > 63 ? closes[closes.length - 64] : closes[0];
        const ret3m = closes.length > 1 && back ? closes[closes.length - 1] / back - 1 : null;
        return { c, s, closes, ret3m, ret1d: s?.ret_1d ?? null, volRatio: s?.vol_ratio_20d ?? null };
      }),
    [feed],
  );
  const alerts = useMemo(() => computeAlerts(feed, rules), [feed, rules]);
  const unreadBy = useMemo(() => {
    const m = new Map<string, number>();
    alerts.filter((a) => !read.includes(a.key)).forEach((a) => m.set(a.symbol, (m.get(a.symbol) ?? 0) + 1));
    return m;
  }, [alerts, read]);

  const sorted = useMemo(() => {
    const val = (r: (typeof rows)[number]) => (sort.key === "symbol" ? r.c.symbol : sort.key === "weight" ? r.c.weight ?? 0 : r[sort.key] ?? -Infinity);
    return [...rows].sort((a, b) => {
      const va = val(a), vb = val(b);
      if (typeof va === "string" && typeof vb === "string") return va.localeCompare(vb) * sort.dir;
      return ((va as number) - (vb as number)) * sort.dir;
    });
  }, [rows, sort]);

  const priced = rows.filter((r) => r.ret1d !== null);
  const totalW = priced.reduce((n, r) => n + (r.c.weight ?? 0), 0);
  const dayMove = totalW ? priced.reduce((n, r) => n + (r.c.weight ?? 0) * (r.ret1d ?? 0), 0) / totalW : null;
  const up = priced.filter((r) => (r.ret1d ?? 0) > 0).length;
  const toggle = (key: SortKey) => setSort((s) => (s.key === key ? { key, dir: (s.dir * -1) as 1 | -1 } : { key, dir: key === "symbol" ? 1 : -1 }));
  const ariaSort = (key: SortKey) => (sort.key === key ? (sort.dir === 1 ? "ascending" : "descending") : "none");

  return (
    <div className="space-y-6">
      <header className="space-y-3">
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <h1 className="text-lg font-semibold">Portfolio</h1>
          <span className="flex items-center gap-2">
            {feed.dataset === "fixture" && <DatasetBadge dataset="fixture" />}
            <ClassTag kind="reported">End of day{feed.eod_date ? `, ${feed.eod_date}` : ""}</ClassTag>
          </span>
        </div>
        <dl className="num grid grid-cols-3 gap-px overflow-hidden rounded-lg border border-line bg-line">
          <Stat term="Weighted day move" value={<span className={signClass(dayMove)}>{pct(dayMove, 2)}</span>} />
          <Stat term="Up / down" value={<>{up}<span className="text-ink-3"> / </span>{priced.length - up}</>} />
          <Stat term="Unread alerts" value={<Link href="/alerts" className={unreadBy.size ? "text-alert hover:underline" : "text-ink-2"}>{unreadBy.size} {unreadBy.size === 1 ? "holding" : "holdings"}</Link>} />
        </dl>
        {priced.length < rows.length && (
          <p className="text-xs text-alert">No price data for {rows.filter((r) => r.ret1d === null).map((r) => r.c.symbol).join(", ")} on the last run; they are excluded from the day move.</p>
        )}
      </header>

      <div className="-mx-4 sm:mx-0">
        <table className="w-full table-fixed text-sm">
          <caption className="sr-only">Holdings, sortable. Select a row to open its latest market move.</caption>
          <thead>
            <tr className="border-b border-line text-2xs text-ink-3">
              <th scope="col" aria-sort={ariaSort("symbol")} className="py-2 pl-4 text-left font-normal sm:pl-0"><SortButton active={sort.key === "symbol"} dir={sort.dir} onClick={() => toggle("symbol")}>Company</SortButton></th>
              <th scope="col" className="hidden w-[84px] py-2 text-right font-normal sm:table-cell">Close ₹</th>
              <th scope="col" className="w-[76px] py-2 text-right font-normal"><span aria-hidden>Trend</span><span className="sr-only">Price trend</span></th>
              <th scope="col" aria-sort={ariaSort("ret1d")} className="w-[64px] py-2 text-right font-normal"><SortButton active={sort.key === "ret1d"} dir={sort.dir} onClick={() => toggle("ret1d")} align="right">1D</SortButton></th>
              <th scope="col" aria-sort={ariaSort("volRatio")} className="hidden w-[92px] py-2 text-right font-normal sm:table-cell"><SortButton active={sort.key === "volRatio"} dir={sort.dir} onClick={() => toggle("volRatio")} align="right">Vol vs 20D</SortButton></th>
              <th scope="col" aria-sort={ariaSort("ret3m")} className="hidden w-[72px] py-2 text-right font-normal md:table-cell"><SortButton active={sort.key === "ret3m"} dir={sort.dir} onClick={() => toggle("ret3m")} align="right">3M</SortButton></th>
              <th scope="col" aria-sort={ariaSort("weight")} className="hidden w-[72px] py-2 text-right font-normal sm:table-cell"><SortButton active={sort.key === "weight"} dir={sort.dir} onClick={() => toggle("weight")} align="right">Weight</SortButton></th>
              <th scope="col" className="w-[36px] py-2 pr-4 sm:hidden"><span className="sr-only">Open</span></th>
            </tr>
          </thead>
          <tbody>
            {sorted.map(({ c, s, closes, ret3m, ret1d, volRatio }) => {
              const n = unreadBy.get(c.symbol) ?? 0;
              return (
                <tr key={c.symbol} onClick={() => router.push(`/moves/${c.symbol}`)} className="cursor-pointer border-b border-line hover:bg-surface">
                  <td className="py-2.5 pl-4 sm:pl-0">
                    <div className="flex items-center gap-2">
                      <Link href={`/moves/${c.symbol}`} onClick={(e) => e.stopPropagation()} className="inline-flex min-h-6 items-center font-semibold tracking-[0.02em] text-ink hover:text-brass">{c.symbol}</Link>
                      {n > 0 && <span className="num rounded-full bg-alert/15 px-1.5 text-[10px] font-semibold leading-4 text-alert" aria-label={`${n} unread alerts`}>{n}</span>}
                      {c.is_financial && <span className="text-2xs text-ink-3">Lender</span>}
                    </div>
                    <p className="truncate text-xs text-ink-3">{c.name}<span className="hidden md:inline">{c.sector ? `, ${c.sector}` : ""}</span></p>
                    <p className="num text-2xs text-ink-3 sm:hidden">{s ? `₹${rupees(s.close)}, vol ${volRatio !== null ? multiple(volRatio) : "n/a"}, ${c.weight}%` : "No price data"}</p>
                  </td>
                  <td className="num hidden py-2.5 text-right text-ink-2 sm:table-cell">{s ? rupees(s.close) : "n/a"}</td>
                  <td className="py-2.5"><div className="flex justify-end">{closes.length > 1 ? <Sparkline values={closes} width={64} height={20} label={`${c.symbol} adjusted closes, last ${closes.length} sessions`} /> : <span className="text-2xs text-ink-3">n/a</span>}</div></td>
                  <td className={`num py-2.5 text-right ${signClass(ret1d)}`}>{pct(ret1d)}</td>
                  <td className={`num hidden py-2.5 text-right sm:table-cell ${volRatio !== null && volRatio >= rules.volumeMultiple ? "text-alert" : "text-ink-2"}`}>{volRatio !== null ? multiple(volRatio) : "n/a"}</td>
                  <td className={`num hidden py-2.5 text-right md:table-cell ${signClass(ret3m)}`}>{pct(ret3m)}</td>
                  <td className="num hidden py-2.5 text-right text-ink-2 sm:table-cell">{c.weight?.toFixed(1)}%</td>
                  <td className="py-2.5 pr-4 text-right text-ink-3 sm:hidden" aria-hidden>›</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="text-2xs text-ink-3">1D and 3M use adjusted closes. Volume is the session against the mean of the previous 20 sessions and turns amber at your threshold ({rules.volumeMultiple}×).</p>
    </div>
  );
}

function Stat({ term, value }: { term: string; value: React.ReactNode }) {
  return (
    <div className="bg-base px-3 py-2.5">
      <dt className="text-2xs text-ink-3">{term}</dt>
      <dd className="mt-0.5 text-md font-medium text-ink">{value}</dd>
    </div>
  );
}

function SortButton({ active, dir, onClick, children, align = "left" }: { active: boolean; dir: 1 | -1; onClick: () => void; children: React.ReactNode; align?: "left" | "right" }) {
  return (
    <button type="button" onClick={onClick} className={`inline-flex items-center gap-1 ${align === "right" ? "flex-row-reverse" : ""} ${active ? "text-ink" : "hover:text-ink-2"}`}>
      {children}
      <span aria-hidden className={`text-[9px] ${active ? "opacity-100" : "opacity-0"}`}>{dir === 1 ? "▲" : "▼"}</span>
    </button>
  );
}
