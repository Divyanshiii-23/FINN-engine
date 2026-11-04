// Formatting helpers. Indian conventions: ₹ crore, en-IN grouping, IST.

const IST = "Asia/Kolkata";

export function crore(v: number, digits = 1): string {
  return v.toLocaleString("en-IN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function rupees(v: number): string {
  return v.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function pct(v: number | null | undefined, digits = 1, signed = true): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "n/a";
  const s = (v * 100).toFixed(digits);
  if (!signed) return `${s}%`;
  if (v > 0) return `+${s}%`;
  if (v < 0) return `−${s.replace("-", "")}%`;
  return `${s}%`;
}

export function pp(v: number, digits = 1): string {
  const s = Math.abs(v).toFixed(digits);
  return `${v >= 0 ? "+" : "−"}${s} pp`;
}

export function multiple(v: number): string {
  return `${v.toFixed(1)}×`;
}

export function timeIST(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: IST,
  });
}

export function dayIST(iso: string): string {
  return new Date(iso).toLocaleDateString("en-IN", {
    weekday: "short",
    day: "numeric",
    month: "short",
    timeZone: IST,
  });
}

export function dateTimeIST(iso: string): string {
  return `${dayIST(iso)}, ${timeIST(iso)} IST`;
}

/** "18:40" today, "Tue 18:40" this week, otherwise a date. */
export function relativeStamp(iso: string, nowIso: string): string {
  const d = new Date(iso);
  const now = new Date(nowIso);
  const sameDay =
    d.toLocaleDateString("en-CA", { timeZone: IST }) ===
    now.toLocaleDateString("en-CA", { timeZone: IST });
  if (sameDay) return timeIST(iso);
  const days = (now.getTime() - d.getTime()) / 864e5;
  if (days < 6) {
    const wd = d.toLocaleDateString("en-IN", { weekday: "short", timeZone: IST });
    return `${wd} ${timeIST(iso)}`;
  }
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short", timeZone: IST });
}

export function signClass(v: number | null | undefined): string {
  if (v === null || v === undefined || v === 0 || !Number.isFinite(v)) return "text-ink-2";
  return v > 0 ? "text-up" : "text-down";
}
