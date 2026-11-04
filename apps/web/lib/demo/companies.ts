// DEMO DATA. Every company here is fictional. Names, tickers and figures are
// invented for this build and do not describe any real listed company.

import type { Company } from "@/lib/types";

export const DEMO_NOTICE =
  "Demo data: fictional companies, filings and figures. Live NSE/BSE feeds are not connected in this build.";

/** The moment the demo snapshot represents. */
export const DEMO_NOW = "2026-11-04T07:30:00+05:30";
/** Default "last looked" for a fresh device. */
export const DEMO_LAST_LOOKED = "2026-11-03T13:10:00+05:30";
/** Latest end-of-day data in the snapshot. */
export const DEMO_EOD_DATE = "2026-11-03";

export const COMPANIES: Company[] = [
  { symbol: "AURELIA", name: "Aurelia Consumer", sector: "FMCG", size: "Large", isFinancial: false, weight: 10, basePrice: 2312 },
  { symbol: "KESTREL", name: "Kestrel Polymers", sector: "Specialty chemicals", size: "Mid", isFinancial: false, weight: 9, basePrice: 1486, research: "full" },
  { symbol: "HALCYON", name: "Halcyon Infotech", sector: "IT services", size: "Large", isFinancial: false, weight: 9, basePrice: 1742 },
  { symbol: "NGRID", name: "Northgrid Power", sector: "Utilities", size: "Large", isFinancial: false, weight: 8, basePrice: 342 },
  { symbol: "QUANTA", name: "Quanta Electronics", sector: "Electronics manufacturing", size: "Mid", isFinancial: false, weight: 7, basePrice: 1964 },
  { symbol: "SARANG", name: "Sarang Finance", sector: "NBFC", size: "Mid", isFinancial: true, weight: 6.5, basePrice: 618, research: "lender" },
  { symbol: "KAVERI", name: "Kaveri Cement", sector: "Cement", size: "Mid", isFinancial: false, weight: 6.5, basePrice: 3380 },
  { symbol: "VEDIKA", name: "Vedika Pharma", sector: "Pharmaceuticals", size: "Mid", isFinancial: false, weight: 6, basePrice: 1128 },
  { symbol: "TIDEMARK", name: "Tidemark Logistics", sector: "Logistics", size: "Mid", isFinancial: false, weight: 5.5, basePrice: 874 },
  { symbol: "ORBIT", name: "Orbit Auto Components", sector: "Auto components", size: "Mid", isFinancial: false, weight: 5, basePrice: 2045 },
  { symbol: "ANVIL", name: "Anvil Specialty Steel", sector: "Metals", size: "Mid", isFinancial: false, weight: 5, basePrice: 735 },
  { symbol: "MERIDIAN", name: "Meridian Cables", sector: "Electricals", size: "Small", isFinancial: false, weight: 4, basePrice: 512 },
  { symbol: "LOTUS", name: "Lotus Leisure Hotels", sector: "Hotels", size: "Small", isFinancial: false, weight: 4, basePrice: 268 },
  { symbol: "CORAL", name: "Coral Retail", sector: "Retail", size: "Small", isFinancial: false, weight: 4, basePrice: 421 },
  { symbol: "PRAGATI", name: "Pragati Small Finance Bank", sector: "Banking", size: "Small", isFinancial: true, weight: 3.5, basePrice: 96 },
  { symbol: "MONSOON", name: "Monsoon Agritech", sector: "Agri inputs", size: "Small", isFinancial: false, weight: 3.5, basePrice: 188 },
  { symbol: "HELIX", name: "Helix Diagnostics", sector: "Healthcare services", size: "Small", isFinancial: false, weight: 3.5, basePrice: 1310 },
  // Research-only names (not held)
  { symbol: "GRANITE", name: "Granite Ports", sector: "Infrastructure", size: "Mid", isFinancial: false, basePrice: 905 },
  { symbol: "SAFFRON", name: "Saffron Foods", sector: "FMCG", size: "Small", isFinancial: false, basePrice: 377 },
  { symbol: "NIMBUS", name: "Nimbus Software", sector: "IT services", size: "Small", isFinancial: false, basePrice: 644 },
  { symbol: "IRONBRIDGE", name: "Ironbridge Infra", sector: "Construction", size: "Mid", isFinancial: false, basePrice: 1182 },
];

export const HOLDINGS = COMPANIES.filter((c) => c.weight !== undefined);

export function company(symbol: string): Company | undefined {
  return COMPANIES.find((c) => c.symbol === symbol.toUpperCase());
}
