"use client";

import type { Feed } from "@/lib/feed";
import { useFeed } from "@/lib/feed";
import { useStore } from "@/lib/store";
import { TextButton } from "../ui/primitives";
import { safeUrl } from "@/lib/safe-url";

/** Renders children with a loaded feed, or an honest loading / error state. */
export function FeedGate({ children }: { children: (feed: Feed) => React.ReactNode }) {
  const f = useFeed();
  const { hydrated } = useStore();
  if (f.status === "loading" || !hydrated) return <div className="h-64" aria-busy="true" aria-label="Loading feed" />;
  if (f.status === "error") {
    return (
      <section className="rounded-lg border border-line bg-surface p-4">
        <p className="text-md text-ink">{f.code === "NO_FEED" ? "No feed yet" : "The feed couldn't be loaded"}</p>
        <p className="mt-1 text-sm text-ink-2">{f.message}</p>
        <div className="-ml-2 mt-2">
          <TextButton tone="accent" onClick={f.reload}>Try again</TextButton>
        </div>
      </section>
    );
  }
  return <>{children(f.feed)}</>;
}

/** Source line for one filing. Fixtures never show an exchange link. */
export function SourceLinks({ source, compact = false }: { source: { source: string; listing_url: string | null; attachment_url: string | null; fixture: boolean; source_id: string }; compact?: boolean }) {
  const ex = source.source.toUpperCase();
  if (source.fixture) {
    return <span className="text-2xs text-ink-3">{ex}-format synthetic fixture, no exchange link</span>;
  }
  const link = "text-2xs text-brass hover:underline";
  return (
    <span className="inline-flex flex-wrap gap-x-3 text-2xs">
      {safeUrl(source.attachment_url) && (
        <a className={link} href={safeUrl(source.attachment_url)!} target="_blank" rel="noopener noreferrer">
          {compact ? `${ex} filing (PDF)` : `Open the ${ex} filing (PDF)`}
        </a>
      )}
      {safeUrl(source.listing_url) && (
        <a className={link} href={safeUrl(source.listing_url)!} target="_blank" rel="noopener noreferrer">
          {ex} company page
        </a>
      )}
      {!safeUrl(source.attachment_url) && !safeUrl(source.listing_url) && <span className="text-ink-3">{ex} id {source.source_id}, no link provided</span>}
    </span>
  );
}

export function DatasetBadge({ dataset }: { dataset: "live" | "fixture" }) {
  return dataset === "fixture" ? (
    <span className="inline-flex h-5 items-center rounded-[4px] border border-alert/50 px-1.5 text-2xs font-medium text-alert">Test fixtures</span>
  ) : (
    <span className="inline-flex h-5 items-center rounded-[4px] border border-up/40 px-1.5 text-2xs font-medium text-up">Live data</span>
  );
}
