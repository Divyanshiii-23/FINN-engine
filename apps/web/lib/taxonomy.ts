// Announcement categories (ENAM reference, section 1) and default rules.

import type { Category, CategoryRule, Rules } from "./types";

export const CATEGORY_LABEL: Record<Category, string> = {
  results: "Results",
  mna: "M&A",
  fund_raise: "Fund raise",
  management_change: "Management change",
  litigation: "Litigation and regulatory",
  insider_trading: "Insider trading",
  earnings_call: "Earnings calls",
  investor_meetings: "Investor meetings",
  credit_rating: "Credit rating",
  dividend: "Dividends",
  bonus_split: "Bonus and split",
  capex: "Capex",
  press_release: "Press releases and orders",
  postal_ballot: "Postal ballots",
  agm_egm: "AGM and EGM",
  pledging: "Promoter pledging",
  unclassified: "Compliance paperwork",
};

export const CATEGORY_ORDER: Category[] = [
  "results",
  "management_change",
  "credit_rating",
  "litigation",
  "mna",
  "pledging",
  "fund_raise",
  "capex",
  "press_release",
  "insider_trading",
  "earnings_call",
  "dividend",
  "bonus_split",
  "investor_meetings",
  "agm_egm",
  "postal_ballot",
  "unclassified",
];

/** Subtypes with a hard floor in the engine (materiality.FLOORS). */
export const FLOOR_NOTE: Partial<Record<Category, string>> = {
  credit_rating: "Downgrades always interrupt",
  management_change: "Auditor resignations always interrupt",
  pledging: "Pledge invocations always interrupt",
  litigation: "Insolvency proceedings always interrupt",
};

export function defaultRules(): Rules {
  const categories = Object.fromEntries(CATEGORY_ORDER.map((c) => [c, "default" as CategoryRule])) as Record<Category, CategoryRule>;
  return { categories, priceMovePct: 5, volumeMultiple: 2, muted: [] };
}
