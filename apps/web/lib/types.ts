// Shared types. Mirrors the API contracts in the architecture doc so the
// demo layer can be swapped for /api/v1 without touching components.

export type Tier = "interrupt" | "brief" | "routine";

export type Category =
  | "results"
  | "mna"
  | "fund_raise"
  | "management_change"
  | "litigation"
  | "insider_trading"
  | "earnings_call"
  | "investor_meetings"
  | "credit_rating"
  | "dividend"
  | "bonus_split"
  | "capex"
  | "press_release"
  | "postal_ballot"
  | "agm_egm"
  | "pledging"
  | "unclassified";

/** The four kinds of information (AI design doc, section 2). */
export type InfoClass =
  | "reported"
  | "guidance"
  | "assertion"
  | "outlook"
  | "computed"
  | "generated";

export interface Company {
  symbol: string;
  name: string;
  sector: string;
  size: "Large" | "Mid" | "Small";
  isFinancial: boolean;
  /** Portfolio weight in percent; undefined for research-only names. */
  weight?: number;
  basePrice: number;
  /** Research available in this build (demo). */
  research?: "full" | "lender";
}

export interface Evidence {
  id: string;
  infoClass: InfoClass;
  docTitle: string;
  page?: number;
  speaker?: string;
  /** Page text around the quote; `match` is highlighted. */
  context?: { before: string; match: string; after: string };
  formula?: string;
  inputs?: string[];
  note?: string;
}

export interface Filing {
  id: string;
  subject: string;
  filedAt: string; // ISO with offset
}

export interface ResultsRow {
  key: "revenue" | "ebitda" | "pbt" | "pat";
  label: string;
  current: number;
  prevQ: number;
  prevY: number;
  evidenceId: string;
}

export interface ResultsFigures {
  period: string;
  periodLabel: string;
  basis: "Consolidated" | "Standalone";
  rows: ResultsRow[];
  ebitdaFormula: string;
}

export interface PersonProfile {
  name: string;
  role: string;
  effective: string;
  background: string[];
  evidenceId: string;
  outgoing?: string;
}

export type Verdict =
  | "delivered"
  | "ahead"
  | "missed"
  | "pending"
  | "revised"
  | "dropped"
  | "unverifiable"
  | "consistent"
  | "contradicted";

export interface GuidanceLink {
  verdict: Verdict;
  text: string;
  ledgerId: string;
}

export interface EventItem {
  id: string;
  symbol: string;
  category: Category;
  subtype?: string;
  /** Tier from scoring, before the user's category rules. */
  tier: Tier;
  score: number;
  /** Hard floor: always surfaces, whatever the user's category rule says. */
  floor?: boolean;
  title: string;
  reason: string;
  reasonEvidence?: string[];
  summary?: string;
  filings: Filing[];
  results?: ResultsFigures;
  profile?: PersonProfile;
  guidance?: GuidanceLink[];
  facts?: { label: string; value: string; evidenceId?: string }[];
}

export interface PricePoint {
  date: string; // YYYY-MM-DD
  close: number;
  volume: number;
}

export type CategoryRule = "default" | "interrupt" | "brief" | "hide";

export interface Rules {
  categories: Record<Category, CategoryRule>;
  priceMovePct: number;
  volumeMultiple: number;
  muted: string[]; // symbols with market alerts muted
}

export interface AlertItem {
  key: string;
  kind: "event" | "price" | "volume" | "price_volume";
  symbol: string;
  at: string; // ISO
  title: string;
  detail: string;
  explained?: boolean;
  eventId?: string;
  category?: Category;
  ret?: number;
  volRatio?: number;
  z?: number | null;
}
