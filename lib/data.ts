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

function computeAlerts(prices: PriceData, cfg: AlertConfig): Alert[] {
  const latest = prices.history.at(-1);
  if (!latest) return [];
  const out: Alert[] = [];
  const base = { ticker: prices.ticker, date: latest.date, close: latest.close };

  if (latest.vol_guard) {
    out.push({
      ...base,
      type: "volume_unreliable",
      value: latest.vol_ratio ?? 0,
      threshold: cfg.volume_threshold,
      message: `Volume check paused: ${latest.vol_guard}`,
    });
  } else if (latest.vol_ratio != null && latest.vol_ratio >= cfg.volume_threshold) {
    out.push({
      ...base,
      type: "volume_spike",
      value: latest.vol_ratio,
      threshold: cfg.volume_threshold,
      message: `Volume ${latest.vol_ratio}× the prior 20-day average`,
    });
  }

  if (Math.abs(latest.change_pct) >= cfg.price_move_pct) {
    out.push({
      ...base,
      type: "price_move",
      value: latest.change_pct,
      threshold: cfg.price_move_pct,
      message: `Price ${latest.change_pct > 0 ? "up" : "down"} ${Math.abs(latest.change_pct).toFixed(1)}% on the day`,
    });
  }
  return out;
}

/** Assemble the briefing from real pipeline outputs only. */
export function getDigest(windowHours = 24): DigestData {
  const portfolio = getPortfolio();
  const cfg: AlertConfig = portfolio?.alert_config ?? {
    volume_threshold: 2,
    price_move_pct: 3,
    watched_categories: [],
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
    alerts.push(...computeAlerts(p, cfg));
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
    portfolio_summary: summary,
  };
}
