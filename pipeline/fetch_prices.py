"""
FINN Pipeline — Fetch EOD prices and volume from Yahoo Finance.

Outputs: data/prices/{TICKER}.json
Computes: daily change %, 20-day average volume, volume ratio (vol / 20d avg).
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from config import (
    ALL_TICKERS, PRICES_DIR, save_json, ticker_symbol, PORTFOLIO_TICKERS
)


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
            hist = stock.history(period=f"{days}d")

            if hist.empty:
                print(f"  ⚠️  No data for {ticker}")
                continue

            # Compute 20-day SMA of volume
            hist["vol_sma20"] = hist["Volume"].rolling(window=20).mean()
            hist["vol_ratio"] = (hist["Volume"] / hist["vol_sma20"]).round(2)
            hist["change_pct"] = hist["Close"].pct_change().mul(100).round(2)

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
                })

            # Current snapshot
            latest = history[-1] if history else {}
            info = stock.info
            current = {
                "price": latest.get("close"),
                "change_pct": latest.get("change_pct"),
                "volume": latest.get("volume"),
                "vol_ratio": latest.get("vol_ratio"),
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

        # Volume alert
        if latest.get("vol_ratio") and latest["vol_ratio"] >= vol_threshold:
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
