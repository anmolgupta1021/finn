"""
FINN Pipeline — Fetch EOD prices and volume from Yahoo Finance.

Outputs: data/prices/{TICKER}.json
Computes: daily change %, 20-day average volume, volume ratio (vol / 20d avg).
"""

from __future__ import annotations

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from config import (
    ALL_TICKERS, PRICES_DIR, save_json, ticker_symbol, PORTFOLIO_TICKERS,
    VOL_WINDOW, GAP_GUARD_PCT, KNOWN_CORPORATE_ACTIONS,
)


def _volume_guard(hist: pd.DataFrame, ticker: str) -> pd.Series:
    """
    For each row, return None if the volume average is trustworthy, else a
    short reason string. The window checked is the VOL_WINDOW sessions before
    the row plus the row itself.
    """
    gap = hist["Close"].pct_change().abs().mul(100) > GAP_GUARD_PCT
    split = hist["Stock Splits"].fillna(0) != 0 if "Stock Splits" in hist else gap & False
    known = pd.Series(False, index=hist.index)
    for d in KNOWN_CORPORATE_ACTIONS.get(ticker, []):
        known |= hist.index.strftime("%Y-%m-%d") == d

    w = VOL_WINDOW + 1
    gap_w = gap.rolling(w, min_periods=1).max().astype(bool)
    split_w = split.rolling(w, min_periods=1).max().astype(bool)
    known_w = known.rolling(w, min_periods=1).max().astype(bool)
    short = pd.Series(range(len(hist)), index=hist.index) < VOL_WINDOW

    reasons = []
    for i in range(len(hist)):
        if short.iloc[i]:
            reasons.append(f"fewer than {VOL_WINDOW} prior sessions")
        elif known_w.iloc[i]:
            reasons.append("known corporate action in window")
        elif split_w.iloc[i]:
            reasons.append("split/bonus in window")
        elif gap_w.iloc[i]:
            reasons.append(f">{GAP_GUARD_PCT:.0f}% overnight gap in window (possible corporate action)")
        else:
            reasons.append(None)
    return pd.Series(reasons, index=hist.index)


def fetch_prices(tickers: list[str] = None, days: int = 90) -> dict:
    """
    Fetch EOD price history for each ticker.
    Returns dict of {ticker: {ticker, fetched_at, current, history}}.
    """
    tickers = tickers or ALL_TICKERS
    results = {}

    for ticker in tickers:
        print(f"📈 Fetching prices for {ticker}...")
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period=f"{days}d", actions=True)

            if hist.empty:
                print(f"  ⚠️  No data for {ticker}")
                continue

            # EOD only: during market hours yfinance returns today's partial
            # bar. Drop it until NSE has closed (15:30 IST; 16:00 for safety).
            now_ist = pd.Timestamp.now(tz="Asia/Kolkata")
            last_day = hist.index[-1].tz_convert("Asia/Kolkata").date() if hist.index.tz else hist.index[-1].date()
            if last_day == now_ist.date() and now_ist.hour < 16:
                hist = hist.iloc[:-1]
                print(f"  ⏳ Dropped partial intraday bar for {last_day}")

            # Average of the PRIOR 20 sessions (today excluded, so a spike
            # doesn't dilute its own baseline).
            hist["vol_sma20"] = hist["Volume"].shift(1).rolling(window=VOL_WINDOW).mean()
            hist["vol_ratio"] = (hist["Volume"] / hist["vol_sma20"]).round(2)
            hist["change_pct"] = hist["Close"].pct_change().mul(100).round(2)
            hist["vol_guard"] = _volume_guard(hist, ticker)

            history = []
            for date, row in hist.iterrows():
                history.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "open": round(row["Open"], 2),
                    "high": round(row["High"], 2),
                    "low": round(row["Low"], 2),
                    "close": round(row["Close"], 2),
                    "volume": int(row["Volume"]),
                    "change_pct": row["change_pct"] if pd.notna(row["change_pct"]) else 0,
                    "vol_ratio": row["vol_ratio"] if pd.notna(row["vol_ratio"]) else None,
                    # Non-null = volume ratio is unreliable for this day; don't alert on it.
                    "vol_guard": row["vol_guard"],
                })

            # Current snapshot
            latest = history[-1] if history else {}
            info = stock.info
            current = {
                "price": latest.get("close"),
                "change_pct": latest.get("change_pct"),
                "volume": latest.get("volume"),
                "vol_ratio": latest.get("vol_ratio"),
                "vol_guard": latest.get("vol_guard"),
                "market_cap": info.get("marketCap"),
                "name": info.get("longName", info.get("shortName", ticker_symbol(ticker))),
                "sector": info.get("sector", "Unknown"),
                "industry": info.get("industry", "Unknown"),
            }

            data = {
                "ticker": ticker,
                "name": current["name"],
                "sector": current["sector"],
                "fetched_at": datetime.utcnow().isoformat() + "Z",
                "current": current,
                "history": history,
            }

            results[ticker] = data
            save_json(PRICES_DIR / f"{ticker_symbol(ticker)}.json", data)
            print(f"  ✅ {ticker} — {current['name']} — ₹{current['price']}")

        except Exception as e:
            print(f"  ❌ {ticker}: {e}")

    return results


def detect_alerts(tickers: list[str] = None,
                  vol_threshold: float = 2.0,
                  price_threshold: float = 3.0) -> list[dict]:
    """
    Scan cached price data for volume and price alerts.
    Returns list of triggered alerts.
    """
    tickers = tickers or PORTFOLIO_TICKERS
    alerts = []

    for ticker in tickers:
        path = PRICES_DIR / f"{ticker_symbol(ticker)}.json"
        if not path.exists():
            continue

        import json
        data = json.loads(path.read_text())
        if not data.get("history"):
            continue

        latest = data["history"][-1]

        # Volume alert — suppressed (with a visible note) if the window is unreliable
        if latest.get("vol_guard"):
            alerts.append({
                "ticker": ticker,
                "type": "volume_unreliable",
                "value": latest.get("vol_ratio"),
                "threshold": vol_threshold,
                "message": f"Volume check paused: {latest['vol_guard']}",
                "date": latest["date"],
                "close": latest["close"],
            })
        elif latest.get("vol_ratio") and latest["vol_ratio"] >= vol_threshold:
            alerts.append({
                "ticker": ticker,
                "type": "volume_spike",
                "value": latest["vol_ratio"],
                "threshold": vol_threshold,
                "message": f"Volume {latest['vol_ratio']}× the 20-day average",
                "date": latest["date"],
                "close": latest["close"],
            })

        # Price move alert
        if abs(latest.get("change_pct", 0)) >= price_threshold:
            direction = "up" if latest["change_pct"] > 0 else "down"
            alerts.append({
                "ticker": ticker,
                "type": "price_move",
                "value": latest["change_pct"],
                "threshold": price_threshold,
                "message": f"Price {direction} {abs(latest['change_pct']):.1f}% in a day",
                "date": latest["date"],
                "close": latest["close"],
            })

    return alerts


if __name__ == "__main__":
    print("=" * 60)
    print("FINN — Fetching prices and volume data")
    print("=" * 60)
    fetch_prices()
    print("\n" + "=" * 60)
    print("Checking for alerts...")
    alerts = detect_alerts()
    if alerts:
        for a in alerts:
            print(f"  🚨 {a['ticker']}: {a['message']}")
    else:
        print("  No alerts triggered.")
    print("Done.")
