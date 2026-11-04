/**
 * URLs shown as links come from exchange payloads and report files, which FINN does not
 * control. Only plain web links are rendered; `javascript:`, `data:` and other schemes
 * are dropped so a crafted filing record cannot run script in the terminal.
 */
export function safeUrl(u: string | null | undefined): string | null {
  if (!u) return null;
  try {
    const p = new URL(u);
    return p.protocol === "https:" || p.protocol === "http:" ? p.href : null;
  } catch {
    return null;
  }
}
