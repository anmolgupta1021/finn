"use client";

import { useState } from "react";
import { cn, displayTicker } from "@/lib/utils";
import type { ResearchData, QuarterAnalysis } from "@/lib/types";
import {
  ArrowUpRight,
  ChevronDown,
  ChevronRight,
  Target,
  TrendingUp,
  TrendingDown,
  Minus,
  FileText,
  AlertCircle,
  CheckCircle,
  XCircle,
  X,
  BarChart3,
  Scale,
} from "lucide-react";

function VerdictBadge({ verdict }: { verdict: string }) {
  switch (verdict) {
    case "beat":
      return (
        <span className="finn-badge-green flex items-center gap-0.5">
          <CheckCircle className="w-2.5 h-2.5" />
          BEAT
        </span>
      );
    case "miss":
      return (
        <span className="finn-badge-red flex items-center gap-0.5">
          <XCircle className="w-2.5 h-2.5" />
          MISS
        </span>
      );
    default:
      return (
        <span className="finn-badge-amber flex items-center gap-0.5">
          <Minus className="w-2.5 h-2.5" />
          HIT
        </span>
      );
  }
}

function QuarterCard({ quarter }: { quarter: QuarterAnalysis }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="finn-card">
      <div
        className="flex items-center justify-between cursor-pointer"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold font-mono">
            {quarter.quarter}
          </span>
          <VerdictBadge verdict={quarter.verdict} />
        </div>
        {expanded ? (
          <ChevronDown className="w-4 h-4 text-finn-muted" />
        ) : (
          <ChevronRight className="w-4 h-4 text-finn-muted" />
        )}
      </div>

      {expanded && (
        <div className="mt-2 space-y-2">
          {/* Guided vs Delivered comparison */}
          {quarter.guided.map((g, i) => {
            const delivered = quarter.delivered[i];
            return (
              <div
                key={i}
                className="bg-finn-surface rounded-lg p-2 space-y-1"
              >
                <div className="text-2xs font-medium text-finn-accent">
                  {g.metric}
                </div>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div>
                    <span className="text-2xs text-finn-muted block">
                      Guided
                    </span>
                    <span className="text-finn-text">{g.guidance}</span>
                    <span className="text-2xs text-finn-muted block mt-0.5 italic">
                      {g.source}
                    </span>
                  </div>
                  {delivered && (
                    <div>
                      <span className="text-2xs text-finn-muted block">
                        Delivered
                      </span>
                      <span className="text-finn-text">{delivered.actual}</span>
                      <span className="text-2xs text-finn-muted block mt-0.5 italic">
                        {delivered.source}
                      </span>
                    </div>
                  )}
                </div>
              </div>
            );
          })}

          {/* Commentary */}
          <p className="text-xs text-finn-muted leading-relaxed border-t border-finn-border pt-2">
            {quarter.commentary}
          </p>
        </div>
      )}
    </div>
  );
}

export function ResearchPanel({
  data,
  onClose,
}: {
  data: ResearchData;
  onClose: () => void;
}) {
  const [activeTab, setActiveTab] = useState<
    "narrative" | "snapshot" | "bull_bear"
  >("narrative");
  const nvn = data.narrative_vs_numbers;
  const ticker = displayTicker(data.ticker);

  const credibilityColor =
    nvn.credibility_score === "high"
      ? "text-green-400"
      : nvn.credibility_score === "medium"
      ? "text-amber-400"
      : "text-red-400";

  const tabs = [
    { id: "narrative" as const, label: "Narrative vs Numbers", icon: Target },
    ...(data.financial_snapshot
      ? [{ id: "snapshot" as const, label: "Snapshot", icon: BarChart3 }]
      : []),
    ...(data.bull_bear
      ? [{ id: "bull_bear" as const, label: "Bull / Bear", icon: Scale }]
      : []),
  ];

  return (
    <div className="fixed inset-0 z-50 bg-finn-bg flex flex-col max-w-[430px] mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-finn-border">
        <div>
          <h2 className="text-base font-bold">{ticker}</h2>
          <p className="text-2xs text-finn-muted">
            {data.company_name || ticker} · Research
          </p>
        </div>
        <button
          onClick={onClose}
          className="w-8 h-8 rounded-full bg-finn-surface flex items-center justify-center"
        >
          <X className="w-4 h-4 text-finn-muted" />
        </button>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-finn-border px-4">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={cn(
              "flex items-center gap-1 px-3 py-2 text-xs font-medium border-b-2 transition-colors",
              activeTab === tab.id
                ? "border-finn-accent text-finn-accent"
                : "border-transparent text-finn-muted hover:text-finn-text"
            )}
          >
            <tab.icon className="w-3 h-3" />
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {activeTab === "narrative" && (
          <>
            {/* Verdict summary */}
            <div className="finn-card bg-finn-surface">
              <div className="flex items-center justify-between mb-1">
                <span className="finn-section-title mb-0">
                  Management credibility
                </span>
                <span
                  className={cn(
                    "text-xs font-semibold uppercase",
                    credibilityColor
                  )}
                >
                  {nvn.credibility_score}
                </span>
              </div>
              <p className="text-sm leading-snug">{nvn.summary}</p>
              {nvn.pattern && (
                <p className="text-xs text-finn-muted mt-2 pt-2 border-t border-finn-border leading-relaxed">
                  <span className="font-medium text-finn-accent">
                    Pattern:
                  </span>{" "}
                  {nvn.pattern}
                </p>
              )}
            </div>

            {/* Quarter-by-quarter */}
            <div className="finn-section-title">Quarter-by-quarter</div>
            <div className="space-y-2">
              {nvn.quarters.map((q) => (
                <QuarterCard key={q.quarter} quarter={q} />
              ))}
            </div>

            {/* Sources & Citation Audit */}
            <div className="flex items-center justify-between mt-4">
              <div className="finn-section-title mb-0">
                Primary Sources ({data.source_documents?.length ?? 0})
              </div>
              {data.citation_audit && (
                <span className="text-2xs font-mono text-emerald-400 bg-emerald-500/10 px-1.5 py-0.5 rounded">
                  {data.citation_audit.pages_actually_read}pp read ·{" "}
                  {data.citation_audit.verified_claims} cited ·{" "}
                  {data.citation_audit.rejected_claims} rejected
                </span>
              )}
            </div>
            <div className="space-y-1.5">
              {data.source_documents?.map((doc, i) => {
                const label =
                  doc.type === "annual_report"
                    ? `Annual Report ${doc.year || ""}`
                    : doc.type === "results_filing"
                    ? `Results Filing ${doc.quarter || ""}`
                    : `Concall Transcript ${doc.quarter || ""}`;
                return (
                  <a
                    key={i}
                    href={doc.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center justify-between gap-2 text-xs text-finn-muted hover:text-finn-accent transition-colors bg-finn-surface/60 px-2.5 py-1.5 rounded-lg"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <FileText className="w-3.5 h-3.5 flex-shrink-0 text-finn-accent" />
                      <span className="truncate">{label.trim()}</span>
                      {doc.pages && (
                        <span className="text-2xs font-mono flex-shrink-0">
                          ({doc.pages}p)
                        </span>
                      )}
                    </div>
                    <ArrowUpRight className="w-3 h-3 flex-shrink-0" />
                  </a>
                );
              })}
            </div>

            {/* Model info */}
            <div className="text-2xs text-finn-muted text-center pt-2 border-t border-finn-border">
              Generated by {data.model_used} · {data.tokens.in.toLocaleString()}
              + {data.tokens.out.toLocaleString()} tokens · ${data.cost_estimate_usd.toFixed(4)}
            </div>
          </>
        )}

        {activeTab === "snapshot" && data.financial_snapshot && (
          <div className="space-y-3">
            <div className="finn-section-title">Financial Snapshot</div>
            <div className="grid grid-cols-2 gap-2">
              {Object.entries(data.financial_snapshot).map(([key, value]) => (
                <div key={key} className="finn-card py-2">
                  <div className="text-2xs text-finn-muted uppercase">
                    {key.replace(/_/g, " ")}
                  </div>
                  <div className="text-sm font-semibold font-mono mt-0.5">
                    {typeof value === "number" && key.includes("ratio")
                      ? value.toFixed(2) + "×"
                      : String(value)}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {activeTab === "bull_bear" && data.bull_bear && (
          <div className="space-y-3">
            <div className="finn-card border-l-2 border-l-green-400">
              <div className="flex items-center gap-1.5 mb-1.5">
                <TrendingUp className="w-3.5 h-3.5 text-green-400" />
                <span className="text-xs font-semibold text-green-400">
                  Bull Case
                </span>
              </div>
              <p className="text-sm leading-relaxed">{data.bull_bear.bull}</p>
            </div>
            <div className="finn-card border-l-2 border-l-red-400">
              <div className="flex items-center gap-1.5 mb-1.5">
                <TrendingDown className="w-3.5 h-3.5 text-red-400" />
                <span className="text-xs font-semibold text-red-400">
                  Bear Case
                </span>
              </div>
              <p className="text-sm leading-relaxed">{data.bull_bear.bear}</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
