/**
 * Server-side data loading.
 *
 * Nothing here is hand-written demo content: the digest is assembled at
 * request time from whatever the pipeline has actually produced in /data.
 * Missing inputs produce empty sections, never placeholder content.
 */

import fs from "fs";
import path from "path";
import type {
  Alert,
  Announcement,
  AlertConfig,
  DigestData,
  PriceData,
  PortfolioTicker,
  ResearchData,
  Stock,
} from "./types";

const DATA_DIR = path.join(process.cwd(), "data");

function readJSON<T>(filePath: string): T | null {
  try {
    return JSON.parse(fs.readFileSync(filePath, "utf-8")) as T;
  } catch {
    return null;
  }
}

const symbolOf = (ticker: string) => ticker.replace(/\.(NS|BO)$/, "");

export function getPortfolio(): { stocks: Stock[]; alert_config: AlertConfig } | null {
  return readJSON(path.join(DATA_DIR, "portfolio.json"));
}

export function getPrices(ticker: string): PriceData | null {
  return readJSON<PriceData>(path.join(DATA_DIR, "prices", `${symbolOf(ticker)}.json`));
}

export function getResearch(ticker: string): ResearchData | null {
  return readJSON<ResearchData>(path.join(DATA_DIR, "research", `${symbolOf(ticker)}.json`));
}

export function getAvailableResearch(): string[] {
  try {
    return fs
      .readdirSync(path.join(DATA_DIR, "research"))
      .filter((f) => f.endsWith(".json"))
      .map((f) => f.replace(".json", ""));
  } catch {
    return [];
  }
}

function getAnnouncements(ticker: string): Announcement[] {
  return readJSON<Announcement[]>(path.join(DATA_DIR, "announcements", `${symbolOf(ticker)}.json`)) ?? [];
}

export function computeAlerts(
  prices: PriceData,
  annsInWindow: Announcement[],
  cfg: AlertConfig,
  windowHours: number
): Alert[] {
  const latest = prices.history.at(-1);
  if (!latest) return [];
  const out: Alert[] = [];

  // 1. Evaluate trading sessions within the selected lookback window
  //    (24h = latest trading session; 3d/7d/14d/30d = sessions within windowHours of latest session date)
  const latestMs = Date.parse(`${latest.date}T16:00:00+05:30`);
  const sessionCutoffMs = latestMs - windowHours * 3600 * 1000;
  const sessionsInWindow =
    windowHours <= 24
      ? [latest]
      : prices.history.filter((pt) => {
          const ptMs = Date.parse(`${pt.date}T16:00:00+05:30`);
          return !Number.isNaN(ptMs) && ptMs >= sessionCutoffMs;
        });

  if (latest.vol_guard) {
    out.push({
      ticker: prices.ticker,
      date: latest.date,
      close: latest.close,
      type: "volume_unreliable",
      value: latest.vol_ratio ?? 0,
      threshold: cfg.volume_threshold,
      message: `Volume check paused: ${latest.vol_guard}`,
    });
  } else {
    // Pick the highest volume spike session in the selected window that crosses cfg.volume_threshold
    let maxVolSession = null as (typeof sessionsInWindow)[number] | null;
    for (const pt of sessionsInWindow) {
      if (!pt.vol_guard && pt.vol_ratio != null && pt.vol_ratio >= cfg.volume_threshold) {
        if (!maxVolSession || (pt.vol_ratio ?? 0) > (maxVolSession.vol_ratio ?? 0)) {
          maxVolSession = pt;
        }
      }
    }
    if (maxVolSession && maxVolSession.vol_ratio != null) {
      const dateSuffix = windowHours > 24 ? ` on ${maxVolSession.date}` : "";
      out.push({
        ticker: prices.ticker,
        date: maxVolSession.date,
        close: maxVolSession.close,
        type: "volume_spike",
        value: maxVolSession.vol_ratio,
        threshold: cfg.volume_threshold,
        message: `Volume ${maxVolSession.vol_ratio}× the prior 20-day average (≥${cfg.volume_threshold}×)${dateSuffix}`,
      });
    }
  }

  // 2. Pick the largest single-day % price move in the selected window that crosses ±cfg.price_move_pct
  let maxMoveSession = null as (typeof sessionsInWindow)[number] | null;
  for (const pt of sessionsInWindow) {
    if (Math.abs(pt.change_pct) >= cfg.price_move_pct) {
      if (!maxMoveSession || Math.abs(pt.change_pct) > Math.abs(maxMoveSession.change_pct)) {
        maxMoveSession = pt;
      }
    }
  }
  if (maxMoveSession) {
    const dateSuffix = windowHours > 24 ? ` on ${maxMoveSession.date}` : " on the day";
    out.push({
      ticker: prices.ticker,
      date: maxMoveSession.date,
      close: maxMoveSession.close,
      type: "price_move",
      value: maxMoveSession.change_pct,
      threshold: cfg.price_move_pct,
      message: `Price ${maxMoveSession.change_pct > 0 ? "up" : "down"} ${Math.abs(maxMoveSession.change_pct).toFixed(1)}%${dateSuffix} (≥±${cfg.price_move_pct}%)`,
    });
  }

  // 3. Emit announcement-triggered alerts for watched categories inside the selected window
  const watchedSet = new Set(cfg.watched_categories ?? []);
  for (const ann of annsInWindow) {
    if (watchedSet.has(ann.category) && ann.priority <= 2) {
      const catLabel = ann.category.replace(/_/g, " ").toUpperCase();
      out.push({
        ticker: prices.ticker,
        date: ann.timestamp.slice(0, 10),
        close: latest.close,
        type: "material_announcement",
        value: ann.priority,
        threshold: 1,
        category: ann.category,
        source_url: ann.source_url,
        message: `[${catLabel}] ${ann.summary}`,
      });
    }
  }

  return out;
}

/** Assemble the briefing from real pipeline outputs only. */
export function getDigest(
  windowHours = 24,
  customConfig?: Partial<AlertConfig>
): DigestData {
  const portfolio = getPortfolio();
  const baseCfg: AlertConfig = portfolio?.alert_config ?? {
    volume_threshold: 2,
    price_move_pct: 3,
    watched_categories: ["results", "M&A", "management_change", "insider_trading", "litigation"],
  };
  const cfg: AlertConfig = {
    volume_threshold:
      customConfig?.volume_threshold != null && !Number.isNaN(customConfig.volume_threshold)
        ? customConfig.volume_threshold
        : baseCfg.volume_threshold,
    price_move_pct:
      customConfig?.price_move_pct != null && !Number.isNaN(customConfig.price_move_pct)
        ? customConfig.price_move_pct
        : baseCfg.price_move_pct,
    watched_categories:
      customConfig?.watched_categories ?? baseCfg.watched_categories,
  };
  const held = (portfolio?.stocks ?? []).filter((s) => s.in_portfolio);

  const summary: PortfolioTicker[] = [];
  const alerts: Alert[] = [];
  const announcements: Announcement[] = [];
  const missingPrices: string[] = [];
  let pricesAsOf: string | null = null;
  let totalOnDisk = 0;

  const cutoff = Date.now() - windowHours * 3600 * 1000;

  for (const s of held) {
    const p = getPrices(s.ticker);
    const allTickerAnns = getAnnouncements(s.ticker);
    totalOnDisk += allTickerAnns.length;
    const anns = allTickerAnns.filter((a) => {
      const t = Date.parse(a.timestamp);
      return Number.isNaN(t) || t >= cutoff;
    });
    announcements.push(...anns);

    if (!p || !p.history.length) {
      missingPrices.push(s.ticker);
      continue;
    }
    const latest = p.history.at(-1)!;
    if (!pricesAsOf || latest.date > pricesAsOf) pricesAsOf = latest.date;
    summary.push({
      ticker: s.ticker,
      name: s.name,
      price: latest.close,
      change_pct: latest.change_pct,
      has_announcement: anns.length > 0,
    });
    alerts.push(...computeAlerts(p, anns, cfg, windowHours));
  }

  announcements.sort((a, b) => a.priority - b.priority || b.timestamp.localeCompare(a.timestamp));

  const windowLabel =
    windowHours >= 24 && windowHours % 24 === 0
      ? `${windowHours / 24}d`
      : `${windowHours}h`;

  return {
    generated_at: new Date().toISOString(),
    window: windowLabel,
    prices_as_of: pricesAsOf,
    missing_prices: missingPrices,
    announcements_ingested: totalOnDisk > 0,
    material: announcements.filter((a) => a.priority === 1),
    notable: announcements.filter((a) => a.priority === 2),
    routine: announcements.filter((a) => a.priority === 3),
    alerts,
    alert_config: cfg,
    portfolio_summary: summary,
  };
}
