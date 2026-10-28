"use client";

import { useEffect, useState } from "react";
import { PortfolioStrip } from "@/components/briefing/portfolio-strip";
import { AnnouncementCard } from "@/components/briefing/announcement-card";
import { AlertsBanner } from "@/components/briefing/alerts-banner";
import { AlertSettingsPanel, loadStoredAlertConfig } from "@/components/briefing/alert-settings";
import { CommandBar } from "@/components/command-bar";
import type { AlertConfig, DigestData } from "@/lib/types";
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

const WINDOW_OPTIONS = [
  { label: "24h", hours: 24 },
  { label: "3d", hours: 24 * 3 },
  { label: "7d", hours: 24 * 7 },
  { label: "30d", hours: 24 * 30 },
];

export function BriefingPage({
  digest: initialDigest,
  initialHours = 24,
  initialResearch = null,
}: {
  digest: DigestData;
  initialHours?: number;
  initialResearch?: import("@/lib/types").ResearchData | null;
}) {
  const [digest, setDigest] = useState<DigestData>(initialDigest);
  const [selectedHours, setSelectedHours] = useState<number>(initialHours);
  const [loadingWindow, setLoadingWindow] = useState(false);
  const [showRoutine, setShowRoutine] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [alertConfig, setAlertConfig] = useState<AlertConfig>(initialDigest.alert_config);
  const windowLabel = digest.window;

  async function refetch(hours: number, cfg: AlertConfig) {
    setLoadingWindow(true);
    try {
      const qs = new URLSearchParams({
        hours: String(hours),
        vol: String(cfg.volume_threshold),
        price: String(cfg.price_move_pct),
        cats: cfg.watched_categories.join(","),
      });
      const res = await fetch(`/api/digest?${qs.toString()}`);
      if (res.ok) {
        const nextDigest = (await res.json()) as DigestData;
        setDigest(nextDigest);
      }
    } finally {
      setLoadingWindow(false);
    }
  }

  // Apply persisted settings on first load
  useEffect(() => {
    const stored = loadStoredAlertConfig();
    if (stored) {
      const merged: AlertConfig = { ...initialDigest.alert_config, ...stored };
      setAlertConfig(merged);
      refetch(24, merged);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleWindowChange(hours: number) {
    setSelectedHours(hours);
    await refetch(hours, alertConfig);
  }

  async function handleSaveSettings(cfg: AlertConfig) {
    setAlertConfig(cfg);
    setShowSettings(false);
    await refetch(selectedHours, cfg);
  }

  const now = new Date();
  const dateStr = new Intl.DateTimeFormat("en-IN", {
    timeZone: "Asia/Kolkata",
    weekday: "short",
    day: "numeric",
    month: "short",
  }).format(now);
  const istHour = parseInt(
    new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", hour: "numeric", hour12: false }).format(now),
    10
  );
  const greeting =
    istHour < 12
      ? "Good morning"
      : istHour < 17
      ? "Good afternoon"
      : "Good evening";
  const timeStr = new Intl.DateTimeFormat("en-IN", {
    timeZone: "Asia/Kolkata",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  }).format(now);

  const materialCount = digest.material.length;
  const alertCount = digest.alerts.filter((a) => a.type !== "volume_unreliable").length;

  return (
    <div className="min-h-screen pb-20">
      {/* ─── Header ─── */}
      <header className="px-4 pt-4 pb-2">
        <div className="flex items-center justify-between mb-1">
          <div>
            <h1 className="text-lg font-bold tracking-tight">FINN</h1>
            <p className="text-2xs text-finn-muted" suppressHydrationWarning>
              {greeting} · {dateStr} · {timeStr}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <div className="relative" aria-label={`${alertCount} alerts`}>
              <Bell className="w-5 h-5 text-finn-muted" />
              {alertCount > 0 && (
                <span className="absolute -top-1.5 -right-1.5 min-w-[16px] h-4 px-1 rounded-full bg-red-500 text-white text-[9px] font-bold flex items-center justify-center">
                  {alertCount}
                </span>
              )}
            </div>
            <button
              onClick={() => setShowSettings((s) => !s)}
              aria-label="Alert settings"
              aria-expanded={showSettings}
              className={cn(
                "w-7 h-7 rounded-full flex items-center justify-center",
                showSettings ? "bg-finn-accent" : "bg-finn-surface"
              )}
            >
              <Settings className={cn("w-3.5 h-3.5", showSettings ? "text-white" : "text-finn-muted")} />
            </button>
          </div>
        </div>

        {/* Window + data freshness */}
        <div className="flex items-center justify-between gap-2 mt-1.5 flex-wrap">
          <div className="flex items-center gap-1.5 flex-wrap">
            <Clock className="w-3 h-3 text-finn-muted" />
            <span className="text-2xs text-finn-muted">
              {loadingWindow ? "Loading…" : `Window ${windowLabel}`}
            </span>
            <span className="text-2xs text-finn-muted">·</span>
            <span className="text-2xs text-finn-muted">
              {digest.prices_as_of ? `EOD prices ${digest.prices_as_of}` : "no price data"}
            </span>
            {materialCount > 0 && (
              <>
                <span className="text-2xs text-finn-muted">·</span>
                <span className="text-2xs text-finn-accent">{materialCount} material</span>
              </>
            )}
          </div>
          <div className="flex items-center gap-1 bg-finn-surface rounded-lg p-0.5 border border-finn-border">
            {WINDOW_OPTIONS.map((opt) => (
              <button
                key={opt.hours}
                onClick={() => handleWindowChange(opt.hours)}
                className={cn(
                  "px-2 py-0.5 rounded text-2xs font-mono transition-colors",
                  selectedHours === opt.hours
                    ? "bg-finn-accent text-white font-semibold"
                    : "text-finn-muted hover:text-finn-text"
                )}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
      </header>

      {showSettings && (
        <AlertSettingsPanel
          config={alertConfig}
          onSave={handleSaveSettings}
          onClose={() => setShowSettings(false)}
        />
      )}

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
            <p className="text-xs text-finn-muted">
              No thresholds crossed in the {windowLabel} window (volume ≥{alertConfig.volume_threshold}×, price ≥±
              {alertConfig.price_move_pct}%, {alertConfig.watched_categories.length} watched filing types).
            </p>
          )}
        </section>
      )}

      {/* ─── Filings: honest empty state when window has 0 announcements ─── */}
      {digest.material.length === 0 &&
        digest.notable.length === 0 &&
        digest.routine.length === 0 && (
          <EmptyState
            title={`No portfolio filings in the last ${windowLabel}`}
            body={
              digest.announcements_ingested
                ? "No portfolio filings landed inside this window. Widen it to 3d, 7d or 30d (the ingestion window is 30 days)."
                : "The announcement pipeline hasn't produced data yet. Nothing on this screen is placeholder content."
            }
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
      <CommandBar initialResearch={initialResearch} />
    </div>
  );
}
