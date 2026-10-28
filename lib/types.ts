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
  /** Non-null when the 20-day volume baseline is unreliable (e.g. corporate action in window). */
  vol_guard?: string | null;
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

export interface ResultsDerivation {
  basis_note: string;
  revenue_definition: string;
  ebitda_formula: string;
  pbt_basis: string;
  pat_basis: string;
}

export interface ResultsEnrichment {
  status?: "ok" | "corrupted_pdf" | "no_statement_page_found";
  error?: string;
  quarter?: string;
  basis?: "consolidated" | "standalone";
  entity_type?: "corporate" | "bank";
  reported_unit?: string;
  normalised_unit?: string;
  source_page?: number;
  vision_used?: boolean;
  ebitda_status?: "not_applicable" | "reported" | "derived" | "derived_from_schedule_iii";
  revenue_label?: string;
  period_ended?: {
    current?: string;
    previous?: string;
    year_ago?: string;
  };
  column_order?: {
    col_1_header?: string;
    col_2_header?: string;
    col_3_header?: string;
    current_col?: string;
    previous_col?: string;
    year_ago_col?: string;
  };
  row_labels?: Record<string, string | null>;
  revenue?: MetricWithChange;
  ebitda?: MetricWithChange | null;
  operating_profit_ex_provisions?: MetricWithChange | null;
  pbt?: MetricWithChange;
  pat?: MetricWithChange;
  pat_owners?: MetricWithChange | null;
  derivation?: ResultsDerivation;
  validation?: {
    passed: boolean;
    flags: string[];
  };
  highlights?: string;
}

export interface MetricWithChange {
  value: number;
  previous_quarter?: number | null;
  year_ago_quarter?: number | null;
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
  type: "volume_spike" | "price_move" | "volume_unreliable" | "material_announcement";
  value: number;
  threshold: number;
  message: string;
  date: string;
  close: number;
  category?: AnnouncementCategory;
  source_url?: string;
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
  source_url?: string;
  doc_id?: string;
  page?: number;
  evidence_file?: string;
}

export interface DeliveredItem {
  metric: string;
  actual: string;
  source: string;
  source_url?: string;
  doc_id?: string;
  page?: number;
  evidence_file?: string;
}

export interface ResearchData {
  ticker: string;
  company_name?: string;
  generated_at: string;
  source_documents: SourceDocument[];
  narrative_vs_numbers: NarrativeVsNumbers;
  citation_audit?: {
    documents_fetched: number;
    pages_actually_read: number;
    verified_claims: number;
    rejected_claims: number;
  };
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
  prices_as_of: string | null;
  missing_prices: string[];
  announcements_ingested: boolean;
  material: Announcement[];
  notable: Announcement[];
  routine: Announcement[];
  alerts: Alert[];
  alert_config: AlertConfig;
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
