// Stand-in for next/navigation in the static demo: the current route lives in the URL hash.
import { useSyncExternalStore } from "react";
import { fromHash, toHash } from "../routes";

let current = fromHash(typeof location !== "undefined" ? location.hash : "") ?? { name: "brief", path: "/" };
const subs = new Set<() => void>();

export function setRoute(hash: string): boolean {
  const r = fromHash(hash);
  if (!r) return false;
  current = r;
  subs.forEach((f) => f());
  return true;
}

export function currentRoute() {
  return current;
}

export function subscribe(f: () => void) {
  subs.add(f);
  return () => subs.delete(f);
}

export function go(href: string, replace = false) {
  const h = toHash(href);
  if (replace) {
    try {
      history.replaceState(null, "", h);
    } catch {
      /* sandboxed: fall through */
    }
    setRoute(h);
  } else if (location.hash === h) {
    setRoute(h);
  } else {
    location.hash = h; // hashchange updates the route
  }
  window.scrollTo(0, 0);
}

export function usePathname(): string {
  return useSyncExternalStore(subscribe, () => current.path, () => current.path);
}

export function useRouter() {
  return { push: (h: string) => go(h), replace: (h: string) => go(h, true), back: () => history.back(), forward: () => history.forward(), refresh: () => {}, prefetch: () => {} };
}

export function useSearchParams() {
  return new URLSearchParams("query" in current ? current.query : undefined);
}

export function useParams() {
  return {};
}

export function notFound(): never {
  throw new Error("not found");
}
