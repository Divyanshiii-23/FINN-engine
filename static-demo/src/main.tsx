// Static demo entry: the real FINN screens (apps/web/components) under a hash router, with the
// data layer in api.ts standing in for the server. Nothing here changes what a screen shows.
import { StrictMode, useSyncExternalStore } from "react";
import { createRoot } from "react-dom/client";
import { StoreProvider } from "@/lib/store";
import { AppShell } from "@/components/shell/AppShell";
import { BriefScreen } from "@/components/brief/BriefScreen";
import { PortfolioScreen } from "@/components/portfolio/PortfolioScreen";
import { AlertsScreen } from "@/components/alerts/AlertsScreen";
import { ResearchHome } from "@/components/research/ResearchHome";
import { CompanyScreen } from "@/components/research/CompanyScreen";
import { CredibilityScreen } from "@/components/research/Credibility";
import { EventDetailScreen } from "@/components/push/EventDetail";
import { MoveDetailScreen } from "@/components/push/MoveDetail";
import { installApi } from "./api";
import { currentRoute, setRoute, subscribe } from "./shims/navigation";
import { toHash } from "./routes";

installApi();

// The app writes app paths into history in one place (the alerts tab); keep them as hash names.
for (const k of ["pushState", "replaceState"] as const) {
  const orig = history[k].bind(history);
  history[k] = (data: unknown, unused: string, url?: string | URL | null) => {
    const u = typeof url === "string" && url.startsWith("/") ? toHash(url) : url;
    try {
      orig(data, unused, u);
    } catch {
      /* a sandboxed frame may refuse; the route is already in memory */
    }
    if (typeof u === "string" && u.startsWith("#")) setRoute(u);
  };
}

window.addEventListener("hashchange", () => {
  if (!setRoute(location.hash)) {
    // Not a route: an in-page anchor such as #nvn. Scroll to it and keep the current screen.
    document.getElementById(location.hash.slice(1))?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
});

// In-page section links (#nvn, #ask …) scroll without leaving the screen.
document.addEventListener("click", (e) => {
  const a = (e.target as HTMLElement | null)?.closest?.("a[href^='#']") as HTMLAnchorElement | null;
  if (!a) return;
  const id = a.getAttribute("href")!.slice(1);
  if (!setRouteProbe(id) && document.getElementById(id)) {
    e.preventDefault();
    document.getElementById(id)!.scrollIntoView({ behavior: "smooth", block: "start" });
  }
});
function setRouteProbe(id: string) {
  return /^(brief|portfolio|research|alerts(-rules|-status)?|credibility-.+|research-.+|event-[0-9a-f]+|move-.+)$/.test(id);
}

function StaticNotice() {
  return (
    <p className="mb-4 rounded-md border border-line bg-surface px-3 py-2 text-xs text-ink-2">
      <span className="font-medium text-ink">Static demo.</span> Synthetic, labelled test data, served without FINN&apos;s engine: browsing, the brief, alerts,
      the five research reports and their sources all work; Ask FINN and on-demand research for other tickers need the engine (see the README).
    </p>
  );
}

function Screen() {
  const r = useSyncExternalStore(subscribe, currentRoute, currentRoute);
  (window as unknown as { __finnQuery?: URLSearchParams }).__finnQuery = r.name === "alerts" ? r.query : new URLSearchParams();
  const key = r.path + ("query" in r ? `?${r.query}` : "");
  const body = (() => {
    switch (r.name) {
      case "portfolio": return <PortfolioScreen />;
      case "alerts": return <AlertsScreen key={key} />;
      case "research": return <ResearchHome />;
      case "company": return <CompanyScreen key={key} symbol={r.symbol.toUpperCase()} />;
      case "credibility": return <CredibilityScreen key={key} symbol={r.symbol.toUpperCase()} />;
      case "event": return <EventDetailScreen key={key} id={r.id} />;
      case "move": return <MoveDetailScreen key={key} symbol={r.symbol.toUpperCase()} />;
      default: return <BriefScreen />;
    }
  })();
  return (
    <AppShell>
      <StaticNotice />
      {body}
    </AppShell>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <StoreProvider>
      <Screen />
    </StoreProvider>
  </StrictMode>,
);
