/** A query parameter of the current view. The static demo routes on the URL hash and sets
 *  window.__finnQuery; the server-rendered app reads the real query string. */
export function queryParam(name: string): string | null {
  if (typeof window === "undefined") return null;
  const g = (window as unknown as { __finnQuery?: URLSearchParams }).__finnQuery;
  return (g ?? new URLSearchParams(window.location.search)).get(name);
}
