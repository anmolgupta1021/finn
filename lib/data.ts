/**
 * Server-side data loading from JSON fixtures.
 * All data reads go through here — never import JSON directly in components.
 */

import fs from "fs";
import path from "path";
import type {
  DigestData,
  ResearchData,
  PriceData,
  Stock,
  AlertConfig,
} from "./types";

const DATA_DIR = path.join(process.cwd(), "data");

function readJSON<T>(filePath: string): T | null {
  try {
    const raw = fs.readFileSync(filePath, "utf-8");
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

/** Load the daily digest (push mode data). */
export function getDigest(): DigestData | null {
  return readJSON<DigestData>(path.join(DATA_DIR, "digest.json"));
}

/** Load portfolio configuration. */
export function getPortfolio(): {
  stocks: Stock[];
  alert_config: AlertConfig;
} | null {
  return readJSON(path.join(DATA_DIR, "portfolio.json"));
}

/** Load research data for a specific ticker. */
export function getResearch(ticker: string): ResearchData | null {
  // ticker comes as "RELIANCE.NS" — we need "RELIANCE"
  const symbol = ticker.replace(/\.(NS|BO)$/, "");
  const filePath = path.join(DATA_DIR, "research", `${symbol}.json`);
  return readJSON<ResearchData>(filePath);
}

/** Load price data for a specific ticker. */
export function getPrices(ticker: string): PriceData | null {
  const symbol = ticker.replace(/\.(NS|BO)$/, "");
  const filePath = path.join(DATA_DIR, "prices", `${symbol}.json`);
  return readJSON<PriceData>(filePath);
}

/** List all tickers that have research data available. */
export function getAvailableResearch(): string[] {
  const dir = path.join(DATA_DIR, "research");
  try {
    return fs
      .readdirSync(dir)
      .filter((f) => f.endsWith(".json"))
      .map((f) => f.replace(".json", ""));
  } catch {
    return [];
  }
}
