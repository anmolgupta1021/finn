"use client";

import { useState } from "react";
import { PortfolioStrip } from "@/components/briefing/portfolio-strip";
import { AnnouncementCard } from "@/components/briefing/announcement-card";
import { AlertsBanner } from "@/components/briefing/alerts-banner";
import { CommandBar } from "@/components/command-bar";
import type { DigestData } from "@/lib/types";
import {
  ChevronDown,
  ChevronUp,
  Bell,
  Clock,
  Settings,
  Zap,
} from "lucide-react";
import { cn } from "@/lib/utils";

function SectionHeader({
  icon: Icon,
  title,
  count,
  color,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  count: number;
  color?: string;
}) {
  return (
    <div className="flex items-center gap-1.5 mb-2">
      <Icon className={cn("w-3.5 h-3.5", color || "text-finn-muted")} />
      <span className="finn-section-title mb-0">{title}</span>
      <span className="text-2xs text-finn-muted">({count})</span>
    </div>
  );
}

function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <section className="px-4 mb-4">
      <div className="rounded-xl border border-dashed border-finn-border p-4">
        <div className="text-xs font-semibold text-finn-text">{title}</div>
        <p className="text-xs text-finn-muted mt-1 leading-relaxed">{body}</p>
      </div>
    </section>
  );
}

export function BriefingPage({ digest }: { digest: DigestData }) {
  const [showRoutine, setShowRoutine] = useState(false);
  const windowLabel = digest.window;

  const now = new Date();
  const greeting =
    now.getHours() < 12
      ? "Good morning"
      : now.getHours() < 17
      ? "Good afternoon"
      : "Good evening";
  const dateStr = now.toLocaleDateString("en-IN", {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
  const timeStr = now.toLocaleTimeString("en-IN", {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });

  const materialCount = digest.material.length;
  const alertCount = digest.alerts.filter((a) => a.type !== "volume_unreliable").length;

  return (
    <div className="min-h-screen pb-20">
      {/* ─── Header ─── */}
      <header className="px-4 pt-4 pb-2">
        <div className="flex items-center justify-between mb-1">
          <div>
            <h1 className="text-lg font-bold tracking-tight">FINN</h1>
            <p className="text-2xs text-finn-muted">
              {greeting} · {dateStr} · {timeStr}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {alertCount > 0 && (
              <div className="relative">
                <Bell className="w-5 h-5 text-finn-muted" />
                <span className="absolute -top-1 -right-1 w-3.5 h-3.5 rounded-full bg-red-500 text-white text-[8px] font-bold flex items-center justify-center">
                  {alertCount}
                </span>
              </div>
            )}
            <button className="w-7 h-7 rounded-full bg-finn-surface flex items-center justify-center">
              <Settings className="w-3.5 h-3.5 text-finn-muted" />
            </button>
          </div>
        </div>

        {/* Window + data freshness */}
        <div className="flex items-center gap-1.5 mt-1 flex-wrap">
          <Clock className="w-3 h-3 text-finn-muted" />
          <span className="text-2xs text-finn-muted">Last {windowLabel}</span>
          <span className="text-2xs text-finn-muted">·</span>
          <span className="text-2xs text-finn-muted">
            {digest.prices_as_of ? `EOD prices ${digest.prices_as_of}` : "no price data"}
          </span>
          {digest.announcements_ingested && (
            <>
              <span className="text-2xs text-finn-muted">·</span>
              <span className="text-2xs text-finn-accent">{materialCount} material</span>
            </>
          )}
        </div>
      </header>

      {/* ─── Portfolio Strip ─── */}
      {digest.portfolio_summary.length > 0 ? (
        <div className="px-3 mb-3">
          <PortfolioStrip tickers={digest.portfolio_summary} />
        </div>
      ) : (
        <EmptyState
          title="No price data yet"
          body="Run pipeline/fetch_prices.py to pull end-of-day prices from Yahoo Finance."
        />
      )}
      {digest.missing_prices.length > 0 && (
        <p className="px-4 -mt-2 mb-3 text-2xs text-finn-muted">
          No price data for: {digest.missing_prices.join(", ")}
        </p>
      )}

      {/* ─── Alerts ─── */}
      {digest.portfolio_summary.length > 0 && (
        <section className="px-4 mb-4">
          <SectionHeader icon={Zap} title="ALERTS" count={digest.alerts.length} color="text-amber-400" />
          {digest.alerts.length > 0 ? (
            <AlertsBanner alerts={digest.alerts} />
          ) : (
            <p className="text-xs text-finn-muted">No price or volume thresholds crossed on the last session.</p>
          )}
        </section>
      )}

      {/* ─── Filings: honest empty state until the announcement pipeline has run ─── */}
      {!digest.announcements_ingested && (
        <EmptyState
          title="No filings ingested yet"
          body="The BSE announcement pipeline hasn't produced data for this window. Filings will appear here, ranked by materiality, once it runs. Nothing on this screen is placeholder content."
        />
      )}

      {/* ─── What Matters ─── */}
      {digest.material.length > 0 && (
        <section className="px-4 mb-4">
          <SectionHeader
            icon={Zap}
            title="WHAT MATTERS"
            count={digest.material.length}
            color="text-red-400"
          />
          <div className="space-y-2">
            {digest.material.map((ann) => (
              <AnnouncementCard key={ann.id} announcement={ann} />
            ))}
          </div>
        </section>
      )}

      {/* ─── Notable ─── */}
      {digest.notable.length > 0 && (
        <section className="px-4 mb-4">
          <SectionHeader
            icon={Bell}
            title="NOTABLE"
            count={digest.notable.length}
            color="text-amber-400"
          />
          <div className="space-y-2">
            {digest.notable.map((ann) => (
              <AnnouncementCard key={ann.id} announcement={ann} />
            ))}
          </div>
        </section>
      )}

      {/* ─── Routine / Noise (collapsed) ─── */}
      {digest.routine.length > 0 && (
        <section className="px-4 mb-4">
          <button
            onClick={() => setShowRoutine(!showRoutine)}
            className="flex items-center gap-1.5 w-full text-left"
          >
            <span className="finn-section-title mb-0">NOISE</span>
            <span className="text-2xs text-finn-muted">
              ({digest.routine.length})
            </span>
            {showRoutine ? (
              <ChevronUp className="w-3 h-3 text-finn-muted" />
            ) : (
              <ChevronDown className="w-3 h-3 text-finn-muted" />
            )}
          </button>
          {showRoutine && (
            <div className="mt-1.5 pl-1">
              {digest.routine.map((ann) => (
                <AnnouncementCard
                  key={ann.id}
                  announcement={ann}
                  variant="compact"
                />
              ))}
            </div>
          )}
        </section>
      )}

      {/* ─── Command Bar (Pull mode) ─── */}
      <CommandBar />
    </div>
  );
}
