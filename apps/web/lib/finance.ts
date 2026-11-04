// Deterministic finance helpers. Code computes; nothing here is model output.

export interface Quarter {
  period: string; // e.g. "Q2 FY27"
  revenue: number;
  ebitda: number;
  pat: number;
}

export function growth(current: number, base: number): number | null {
  if (!base) return null;
  return current / base - 1;
}

/** Margin over a set of quarters: summed numerator over summed denominator. */
export function summedMargin(qs: Quarter[]): number {
  const rev = qs.reduce((s, q) => s + q.revenue, 0);
  const e = qs.reduce((s, q) => s + q.ebitda, 0);
  return e / rev;
}

export function sum(qs: Quarter[], key: "revenue" | "ebitda" | "pat"): number {
  return qs.reduce((s, q) => s + q[key], 0);
}

/**
 * Margin the remaining half must deliver for the full year to reach `target`,
 * assuming the second half's revenue equals the first half's.
 */
export function requiredH2Margin(h1Margin: number, target: number): number {
  return 2 * target - h1Margin;
}

/** Growth the second half must deliver for full-year growth to reach `target`. */
export function requiredH2Growth(
  h1Current: number,
  h1Prior: number,
  h2Prior: number,
  target: number,
): number {
  const fyTarget = (h1Prior + h2Prior) * (1 + target);
  return (fyTarget - h1Current) / h2Prior - 1;
}

export function mean(xs: number[]): number {
  return xs.reduce((s, x) => s + x, 0) / xs.length;
}
