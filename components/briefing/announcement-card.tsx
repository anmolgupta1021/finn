"use client";

import { cn, displayTicker, formatIndianCurrency, formatChange, timeAgo } from "@/lib/utils";
import type { Announcement, ResultsEnrichment, ManagementEnrichment } from "@/lib/types";
import {
  TrendingUp,
  TrendingDown,
  User,
  Merge,
  AlertTriangle,
  ArrowUpRight,
  ChevronDown,
  ChevronUp,
  Bookmark,
  Star,
} from "lucide-react";
import { useState } from "react";

const CATEGORY_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  results: TrendingUp,
  "M&A": Merge,
  management_change: User,
  litigation: AlertTriangle,
};

const CATEGORY_LABELS: Record<string, string> = {
  results: "Results",
  "M&A": "M&A",
  management_change: "Mgmt Change",
  fund_raise: "Fund Raise",
  litigation: "Litigation",
  insider_trading: "Insider",
  earnings_call: "Earnings Call",
  credit_rating: "Rating",
  dividend: "Dividend",
  capex: "Capex",
  bonus_split: "Bonus/Split",
  pledging: "Pledging",
  press_release: "Press Release",
  investor_meetings: "Investor Meet",
  postal_ballot: "Postal Ballot",
  agm_egm: "AGM/EGM",
  unclassified: "Filing",
};

function ResultsCard({ announcement }: { announcement: Announcement }) {
  const e = announcement.enrichment as ResultsEnrichment;
  if (!e) return null;

  if (e.status && e.status !== "ok") {
    return (
      <div className="mt-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-2.5 text-2xs">
        <div className="font-semibold text-amber-300">
          Extraction skipped ({e.status.replace(/_/g, " ")})
        </div>
        {e.error && <div className="text-finn-muted mt-0.5 font-mono">{e.error}</div>}
        {e.highlights && <div className="text-finn-muted mt-1">{e.highlights}</div>}
      </div>
    );
  }

  if (!e.revenue) return null;

  const isBank = e.entity_type === "bank" || e.ebitda_status === "not_applicable";
  const unitNote =
    e.reported_unit && e.reported_unit !== "crore"
      ? `₹ Cr (from ₹ ${e.reported_unit})`
      : "₹ Cr";

  const rows: {
    label: string;
    data?: ResultsEnrichment["revenue"] | null;
    naNote?: string;
  }[] = [
    { label: e.revenue_label || "Revenue", data: e.revenue },
    isBank
      ? { label: "EBITDA", data: null, naNote: "N/A (Bank format)" }
      : { label: "Operating EBITDA", data: e.ebitda },
    ...(isBank && e.operating_profit_ex_provisions
      ? [{ label: "Op. Profit (ex-prov)", data: e.operating_profit_ex_provisions }]
      : []),
    { label: "PBT", data: e.pbt },
    { label: "PAT", data: e.pat },
  ];

  return (
    <div className="mt-2.5 border-t border-finn-border pt-2">
      {/* Metadata badges */}
      <div className="flex items-center justify-between gap-1.5 flex-wrap mb-2">
        <div className="flex items-center gap-1.5 flex-wrap">
          {e.quarter && (
            <span className="text-2xs font-semibold text-finn-text bg-finn-bg px-1.5 py-0.5 rounded">
              {e.quarter}
            </span>
          )}
          {e.basis && (
            <span className="text-2xs uppercase tracking-wider font-medium text-finn-accent bg-finn-accent/10 px-1.5 py-0.5 rounded">
              {e.basis}
            </span>
          )}
          <span className="text-2xs text-finn-muted font-mono">{unitNote}</span>
        </div>
        {e.validation && (
          <span
            className={cn(
              "text-2xs font-mono px-1.5 py-0.5 rounded",
              e.validation.passed
                ? "text-emerald-400 bg-emerald-500/10"
                : "text-amber-400 bg-amber-500/10"
            )}
          >
            {e.validation.passed
              ? `Verified · p.${e.source_page ?? "?"}`
              : `Flags (${e.validation.flags.length})`}
          </span>
        )}
      </div>

      {/* Metrics table: Metric | Value (₹ Cr) | YoY | QoQ */}
      <div className="rounded-lg bg-finn-bg/70 p-2 space-y-1.5">
        <div className="grid grid-cols-12 text-[10px] text-finn-muted uppercase tracking-wider pb-1 border-b border-finn-border/60">
          <span className="col-span-5">Metric</span>
          <span className="col-span-3 text-right">Current</span>
          <span className="col-span-2 text-right">YoY</span>
          <span className="col-span-2 text-right">QoQ</span>
        </div>
        {rows.map((r) => {
          if (r.naNote) {
            return (
              <div
                key={r.label}
                className="grid grid-cols-12 items-baseline text-xs py-0.5"
              >
                <span className="col-span-5 text-finn-muted">{r.label}</span>
                <span className="col-span-7 text-right text-2xs font-mono text-finn-muted italic">
                  {r.naNote}
                </span>
              </div>
            );
          }
          if (!r.data) return null;
          const yoy = formatChange(r.data.yoy);
          const qoq = formatChange(r.data.qoq);
          return (
            <div
              key={r.label}
              className="grid grid-cols-12 items-baseline text-xs py-0.5"
            >
              <span className="col-span-5 text-finn-muted truncate pr-1">
                {r.label}
              </span>
              <span className="col-span-3 text-right font-mono font-medium">
                {formatIndianCurrency(r.data.value)}
              </span>
              <span
                className={cn("col-span-2 text-right text-2xs font-mono", yoy.className)}
              >
                {yoy.text}
              </span>
              <span
                className={cn("col-span-2 text-right text-2xs font-mono", qoq.className)}
              >
                {qoq.text}
              </span>
            </div>
          );
        })}
      </div>

      {e.highlights && (
        <p className="text-2xs text-finn-muted mt-2 leading-relaxed">
          {e.highlights}
        </p>
      )}
    </div>
  );
}

function ManagementCard({ announcement }: { announcement: Announcement }) {
  const e = announcement.enrichment as ManagementEnrichment;
  if (!e?.person_name) return null;

  return (
    <div className="mt-2 flex gap-2.5">
      <div className="w-8 h-8 rounded-full bg-finn-accent/20 flex items-center justify-center flex-shrink-0">
        <User className="w-4 h-4 text-finn-accent" />
      </div>
      <div className="min-w-0">
        <div className="text-xs font-medium">{e.person_name}</div>
        <div className="text-2xs text-finn-muted">{e.role}</div>
        {e.background && (
          <p className="text-2xs text-finn-muted mt-1 leading-relaxed">
            {e.background}
          </p>
        )}
      </div>
    </div>
  );
}

export function AnnouncementCard({
  announcement,
  variant = "full",
}: {
  announcement: Announcement;
  variant?: "full" | "compact";
}) {
  const [expanded, setExpanded] = useState(false);
  const Icon = CATEGORY_ICONS[announcement.category] || Star;
  const categoryLabel =
    CATEGORY_LABELS[announcement.category] || announcement.category;

  const priorityColor =
    announcement.priority === 1
      ? "border-l-red-400"
      : announcement.priority === 2
      ? "border-l-amber-400"
      : "border-l-finn-border";

  const priorityBadge =
    announcement.priority === 1
      ? "finn-badge-red"
      : announcement.priority === 2
      ? "finn-badge-amber"
      : "finn-badge-muted";

  if (variant === "compact") {
    return (
      <div className="flex items-start gap-2 py-1.5">
        <span className="w-1 h-1 rounded-full bg-finn-muted mt-1.5 flex-shrink-0" />
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="text-2xs text-finn-muted font-medium">
              {displayTicker(announcement.ticker)}
            </span>
            <span className="text-2xs text-finn-muted">·</span>
            <span className="text-2xs text-finn-muted">{categoryLabel}</span>
          </div>
          <p className="text-xs text-finn-muted truncate">
            {announcement.summary || announcement.headline}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "finn-card border-l-2 cursor-pointer transition-all",
        priorityColor
      )}
      onClick={() => setExpanded(!expanded)}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <div
            className={cn(
              "w-6 h-6 rounded-md flex items-center justify-center flex-shrink-0",
              announcement.priority === 1
                ? "bg-red-500/15"
                : announcement.priority === 2
                ? "bg-amber-500/15"
                : "bg-finn-border"
            )}
          >
            <Icon
              className={cn(
                "w-3.5 h-3.5",
                announcement.priority === 1
                  ? "text-red-400"
                  : announcement.priority === 2
                  ? "text-amber-400"
                  : "text-finn-muted"
              )}
            />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-semibold">
                {displayTicker(announcement.ticker)}
              </span>
              <span className={priorityBadge}>{categoryLabel}</span>
            </div>
          </div>
        </div>
        <span className="text-2xs text-finn-muted flex-shrink-0">
          {timeAgo(announcement.timestamp)}
        </span>
      </div>

      {/* Summary — the "so what" line */}
      <p className="text-sm mt-1.5 leading-snug">{announcement.summary}</p>

      {/* Enriched content */}
      {expanded && announcement.category === "results" && (
        <ResultsCard announcement={announcement} />
      )}
      {expanded && announcement.category === "management_change" && (
        <ManagementCard announcement={announcement} />
      )}

      {/* Expand hint for enrichable categories */}
      {(announcement.category === "results" ||
        announcement.category === "management_change") &&
        !expanded && (
          <div className="flex items-center gap-0.5 mt-1.5 text-2xs text-finn-accent">
            <ChevronDown className="w-3 h-3" />
            <span>Tap for details</span>
          </div>
        )}

      {/* Source link */}
      {expanded && announcement.source_url && (
        <div className="mt-2 pt-2 border-t border-finn-border flex items-center justify-between">
          <a
            href={announcement.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-2xs text-finn-accent flex items-center gap-1 hover:underline"
            onClick={(e) => e.stopPropagation()}
          >
            View original filing
            <ArrowUpRight className="w-3 h-3" />
          </a>
          <span className="text-2xs text-finn-muted font-mono">
            {announcement.model_used}
          </span>
        </div>
      )}
    </div>
  );
}
