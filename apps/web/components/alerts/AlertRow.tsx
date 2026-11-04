"use client";

import Link from "next/link";
import type { AlertItem } from "@/lib/types";
import type { Feed } from "@/lib/feed";
import { companyOf } from "@/lib/feed";
import { relativeStamp } from "@/lib/format";
import { useStore } from "@/lib/store";
import { TextButton } from "../ui/primitives";

const KIND_LABEL: Record<AlertItem["kind"], string> = {
  event: "Filing",
  price: "Price move",
  volume: "Volume spike",
  price_volume: "Price and volume",
};

export function alertHref(a: AlertItem) {
  return a.kind === "event" ? `/events/${a.eventId}` : `/moves/${a.symbol}`;
}

export function AlertRow({ a, feed, withActions = true }: { a: AlertItem; feed: Feed; withActions?: boolean }) {
  const { read, markRead, markUnread } = useStore();
  const isRead = read.includes(a.key);
  const market = a.kind !== "event";
  const unexplained = market && !a.explained;
  return (
    <article className="relative border-b border-line py-3 pl-4 last:border-b-0">
      <span aria-hidden className={`absolute bottom-3 left-0 top-3 w-[2px] rounded-full ${isRead ? "bg-line-strong" : "bg-alert"}`} />
      <header className="flex items-baseline justify-between gap-3">
        <div className="flex min-w-0 items-baseline gap-2">
          {!isRead && <span className="sr-only">Unread.</span>}
          <span className="text-sm font-semibold tracking-[0.02em] text-ink">{a.symbol}</span>
          <span className="truncate text-xs text-ink-3">
            {companyOf(feed, a.symbol)?.name ?? a.symbol}, {KIND_LABEL[a.kind].toLowerCase()}
          </span>
        </div>
        <time dateTime={a.at} className="num shrink-0 text-2xs text-ink-3">
          {market ? "End of day" : relativeStamp(a.at, feed.as_of)}
        </time>
      </header>
      <p className={`mt-1 text-sm ${isRead ? "text-ink-2" : "font-medium text-ink"}`}>
        <Link href={alertHref(a)} className="-my-1 inline-block py-1 hover:text-brass" onClick={() => markRead([a.key])}>
          {a.title}
        </Link>
      </p>
      <p className={`mt-0.5 text-xs ${unexplained ? "text-alert" : "text-ink-2"}`}>
        {a.detail}
        {market && a.z !== undefined && a.z !== null && <span className="num text-ink-3"> ({a.z >= 0 ? "+" : ""}{a.z.toFixed(1)} standard deviations)</span>}
      </p>
      {withActions && (
        <div className="-ml-2 mt-1.5 flex flex-wrap gap-x-1">
          <Link href={alertHref(a)} onClick={() => markRead([a.key])} className="inline-flex h-7 items-center rounded-md px-2 text-xs font-medium text-brass hover:bg-brass/10">
            Investigate
          </Link>
          {isRead ? <TextButton onClick={() => markUnread(a.key)}>Mark unread</TextButton> : <TextButton onClick={() => markRead([a.key])}>Mark read</TextButton>}
        </div>
      )}
    </article>
  );
}
