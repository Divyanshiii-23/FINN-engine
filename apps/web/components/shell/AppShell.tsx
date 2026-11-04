"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useMemo, useRef } from "react";
import { useStore } from "@/lib/store";
import { computeAlerts } from "@/lib/push";
import { useFeed } from "@/lib/feed";
import { dateTimeIST } from "@/lib/format";
import { EvidenceSheet } from "../EvidenceSheet";
import { SourceViewer } from "../research/SourceViewer";

type NavKey = "brief" | "portfolio" | "research" | "alerts";

const NAV: { key: NavKey; href: string; label: string }[] = [
  { key: "brief", href: "/", label: "Brief" },
  { key: "portfolio", href: "/portfolio", label: "Portfolio" },
  { key: "research", href: "/research", label: "Research" },
  { key: "alerts", href: "/alerts", label: "Alerts" },
];

function Icon({ k }: { k: NavKey }) {
  const p = { fill: "none", stroke: "currentColor", strokeWidth: 1.5, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  return (
    <svg aria-hidden width="20" height="20" viewBox="0 0 20 20">
      {k === "brief" && (
        <>
          <path {...p} d="M4 5h12M4 10h8M4 15h5" />
          <circle cx="15.5" cy="14.5" r="2" fill="currentColor" />
        </>
      )}
      {k === "portfolio" && (
        <>
          <rect {...p} x="3.5" y="3.5" width="13" height="13" rx="2" />
          <path {...p} d="M3.5 9h13M9 9v7.5" />
        </>
      )}
      {k === "research" && (
        <>
          <circle {...p} cx="9" cy="9" r="5" />
          <path {...p} d="M13 13l3.5 3.5" />
        </>
      )}
      {k === "alerts" && (
        <>
          <path {...p} d="M5.5 13.5V9a4.5 4.5 0 0 1 9 0v4.5l1.5 1.5H4z" />
          <path {...p} d="M8.5 17h3" />
        </>
      )}
    </svg>
  );
}

function active(pathname: string, href: string) {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}

function Wordmark() {
  return (
    <Link href="/" className="flex items-baseline gap-2" aria-label="FINN, go to brief">
      <span className="text-[17px] font-semibold tracking-[0.04em] text-ink">FINN</span>
      <span className="hidden text-2xs text-ink-3 sm:inline lg:hidden">Financial investment agent</span>
    </Link>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  // The phone top bar is sticky and its height varies (the data notice can wrap), so it is
  // published as --topbar for anything else that sticks or scrolls to an anchor below it.
  const topbar = useRef<HTMLElement>(null);
  useEffect(() => {
    const el = topbar.current;
    if (!el) return;
    const set = () => document.documentElement.style.setProperty("--topbar", `${el.offsetHeight}px`);
    set();
    const ro = new ResizeObserver(set);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const pathname = usePathname();
  const { rules, read, hydrated, resetDemo } = useStore();
  const f = useFeed();
  const feed = f.status === "ready" ? f.feed : null;
  const unread = useMemo(
    () => (hydrated && feed ? computeAlerts(feed, rules).filter((a) => !read.includes(a.key)).length : 0),
    [rules, read, hydrated, feed],
  );
  const notice = !feed
    ? f.status === "error" ? "No feed loaded. Run the engine to generate one." : "Loading feed"
    : feed.dataset === "fixture"
      ? "Test fixtures: synthetic filings and prices for fictional companies. Not real exchange data."
      : `Live data from the exchanges and Yahoo Finance, generated ${dateTimeIST(feed.generated_at)}.`;
  const asOf = feed ? `As of ${dateTimeIST(feed.as_of)}` : "";

  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[208px_1fr]">
      {/* Side rail, wide screens */}
      <aside className="sticky top-0 hidden h-dvh flex-col border-r border-line bg-base px-3 py-4 lg:flex">
        <div className="px-2">
          <Wordmark />
          <p className="mt-0.5 text-2xs text-ink-3">Financial investment agent</p>
        </div>
        <nav aria-label="Main" className="mt-6 flex flex-col gap-0.5">
          {NAV.map((n) => {
            const on = active(pathname, n.href);
            return (
              <Link
                key={n.key}
                href={n.href}
                aria-current={on ? "page" : undefined}
                className={`flex h-9 items-center gap-3 rounded-md px-2 text-sm ${
                  on ? "bg-raised text-ink" : "text-ink-2 hover:bg-surface hover:text-ink"
                }`}
              >
                <Icon k={n.key} />
                <span className="flex-1">{n.label}</span>
                {n.key === "alerts" && unread > 0 && (
                  <span className="num rounded-full bg-alert/15 px-1.5 text-2xs font-semibold text-alert">{unread}</span>
                )}
              </Link>
            );
          })}
        </nav>
        <div className="mt-auto space-y-2 px-2 text-2xs text-ink-3">
          <p>{asOf}</p>
          <p className={feed?.dataset === "fixture" ? "text-alert/90" : "text-ink-3/90"}>{notice}</p>
          <button type="button" onClick={resetDemo} className="text-brass hover:underline">
            Reset demo state
          </button>
        </div>
      </aside>

      <div className="min-w-0">
        {/* Top bar, phones and tablets */}
        <header ref={topbar} className="sticky top-0 z-30 border-b border-line bg-base/95 backdrop-blur lg:hidden">
          <div className="flex h-12 items-center justify-between px-4">
            <Wordmark />
            <span className="num text-2xs text-ink-3">{asOf}</span>
          </div>
          <p className={`border-t border-line px-4 py-1.5 text-2xs ${feed?.dataset === "fixture" ? "text-alert/90" : "text-ink-3"}`}>{notice}</p>
        </header>

        <main className="mx-auto w-full max-w-[1120px] px-4 pb-28 pt-5 sm:px-6 lg:px-10 lg:pb-16 lg:pt-8">
          {children}
        </main>
      </div>

      {/* Bottom tabs, phones and tablets */}
      <nav aria-label="Main" className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-base/95 pb-safe backdrop-blur lg:hidden">
        <ul className="grid grid-cols-4">
          {NAV.map((n) => {
            const on = active(pathname, n.href);
            return (
              <li key={n.key}>
                <Link
                  href={n.href}
                  aria-current={on ? "page" : undefined}
                  className={`relative flex h-14 flex-col items-center justify-center gap-0.5 text-2xs ${on ? "text-ink" : "text-ink-3"}`}
                >
                  {on && <span aria-hidden className="absolute top-0 h-0.5 w-8 rounded-full bg-brass" />}
                  <Icon k={n.key} />
                  <span>{n.label}</span>
                  {n.key === "alerts" && unread > 0 && (
                    <span className="num absolute right-[calc(50%-20px)] top-1.5 min-w-4 rounded-full bg-alert px-1 text-center text-[10px] font-semibold leading-4 text-base">
                      {unread}
                    </span>
                  )}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      <EvidenceSheet />
      <SourceViewer />
    </div>
  );
}
