// App paths <-> hash names. The hosted page only passes a plain "#name" (letters, digits, hyphens)
// between its URL and the app, so "/research/HALCYON" becomes "#research-HALCYON".
// "&" in a ticker (M&M) is written "--".

const enc = (s: string) => decodeURIComponent(s).toUpperCase().replace(/&/g, "--");
const dec = (s: string) => s.replace(/--/g, "&");

export function toHash(href: string): string {
  const [path, query = ""] = href.split("?");
  const q = new URLSearchParams(query);
  const p = path.replace(/\/+$/, "") || "/";
  let m: RegExpMatchArray | null;
  if (p === "/") return "#brief";
  if (p === "/portfolio") return "#portfolio";
  if (p === "/alerts") return q.get("tab") === "rules" ? "#alerts-rules" : q.get("tab") === "status" ? "#alerts-status" : "#alerts";
  if (p === "/research") return "#research";
  if ((m = p.match(/^\/research\/([^/]+)\/credibility$/))) return `#credibility-${enc(m[1])}`;
  if ((m = p.match(/^\/research\/([^/]+)$/))) return `#research-${enc(m[1])}`;
  if ((m = p.match(/^\/events\/([^/]+)$/))) return `#event-${m[1]}`;
  if ((m = p.match(/^\/moves\/([^/]+)$/))) return `#move-${enc(m[1])}`;
  return "#brief";
}

export type Route =
  | { name: "brief" | "portfolio" | "research"; path: string }
  | { name: "alerts"; path: string; query: URLSearchParams }
  | { name: "company" | "credibility" | "move"; path: string; symbol: string }
  | { name: "event"; path: string; id: string };

/** null when the hash isn't a route (an in-page anchor such as #nvn). */
export function fromHash(hash: string): Route | null {
  const h = hash.replace(/^#/, "");
  let m: RegExpMatchArray | null;
  if (h === "" || h === "brief") return { name: "brief", path: "/" };
  if (h === "portfolio") return { name: "portfolio", path: "/portfolio" };
  if (h === "research") return { name: "research", path: "/research" };
  if ((m = h.match(/^alerts(?:-(rules|status))?$/))) return { name: "alerts", path: "/alerts", query: new URLSearchParams(m[1] ? { tab: m[1] } : {}) };
  if ((m = h.match(/^credibility-(.+)$/))) return { name: "credibility", path: `/research/${dec(m[1])}/credibility`, symbol: dec(m[1]) };
  if ((m = h.match(/^research-(.+)$/))) return { name: "company", path: `/research/${dec(m[1])}`, symbol: dec(m[1]) };
  if ((m = h.match(/^event-([0-9a-f]+)$/))) return { name: "event", path: `/events/${m[1]}`, id: m[1] };
  if ((m = h.match(/^move-(.+)$/))) return { name: "move", path: `/moves/${dec(m[1])}`, symbol: dec(m[1]) };
  return null;
}
