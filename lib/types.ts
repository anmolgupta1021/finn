/* ─── Shared TypeScript types for FINN ─── */

export interface Stock {
  ticker: string;
  name: string;
  sector: string;
  in_portfolio: boolean;
}

export interface PriceData {
  ticker: string;
  name: string;
  sector: string;
  fetched_at: string;
  current: {
    price: number;
    change_pct: number;
    volume: number;
    vol_ratio: number | null;
    market_cap: number;
    name: string;
    sector: string;
    industry: string;
  };
  history: PricePoint[];
}

export interface PricePoint {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  change_pct: number;
  vol_ratio: number | null;
}

export interface Announcement {
  id: string;
  ticker: string;
  company_name: string;
  timestamp: string;
  headline: string;
  category: AnnouncementCategory;
  priority: 1 | 2 | 3;
  summary: string;
  source_url: string;
  raw_text: string;
  enrichment: ResultsEnrichment | ManagementEnrichment | Record<string, never>;
  model_used: string | null;
  tokens: { in: number; out: number };
}

export type AnnouncementCategory =
  | "results"
  | "M&A"
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

export interface ResultsEnrichment {
  quarter?: string;
  revenue?: MetricWithChange;
  ebitda?: MetricWithChange;
  pbt?: MetricWithChange;
  pat?: MetricWithChange;
  highlights?: string;
}

export interface MetricWithChange {
  value: number;
  qoq: number | null;
  yoy: number | null;
}

export interface ManagementEnrichment {
  person_name?: string;
  role?: string;
  action?: "joined" | "resigned" | "retired";
  background?: string;
}

export interface Alert {
  ticker: string;
  type: "volume_spike" | "price_move";
  value: number;
  threshold: number;
  message: string;
  date: string;
  close: number;
}

export interface NarrativeVsNumbers {
  summary: string;
  quarters: QuarterAnalysis[];
  credibility_score: "high" | "medium" | "low";
  pattern: string;
}

export interface QuarterAnalysis {
  quarter: string;
  guided: GuidanceItem[];
  delivered: DeliveredItem[];
  verdict: "hit" | "miss" | "beat";
  commentary: string;
}

export interface GuidanceItem {
  metric: string;
  guidance: string;
  source: string;
}

export interface DeliveredItem {
  metric: string;
  actual: string;
  source: string;
}

export interface ResearchData {
  ticker: string;
  company_name?: string;
  generated_at: string;
  source_documents: SourceDocument[];
  narrative_vs_numbers: NarrativeVsNumbers;
  financial_snapshot?: Record<string, unknown>;
  cash_quality?: Record<string, unknown>;
  bull_bear?: { bull: string; bear: string };
  model_used: string;
  tokens: { in: number; out: number };
  cost_estimate_usd: number;
}

export interface SourceDocument {
  type: "annual_report" | "concall_transcript" | "results_filing";
  year?: string;
  quarter?: string;
  url: string;
  pages?: number;
}

export interface DigestData {
  generated_at: string;
  window: string;
  material: Announcement[];
  notable: Announcement[];
  routine: Announcement[];
  alerts: Alert[];
  portfolio_summary: PortfolioTicker[];
}

export interface PortfolioTicker {
  ticker: string;
  name: string;
  price: number;
  change_pct: number;
  has_announcement: boolean;
}

export interface AlertConfig {
  volume_threshold: number;
  price_move_pct: number;
  watched_categories: AnnouncementCategory[];
}
