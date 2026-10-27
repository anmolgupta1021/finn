"""
Verify every configured ticker with a real yfinance call (not web search).
Prints raw results; exits non-zero if any ticker fails.
"""
from __future__ import annotations

import sys
import warnings

warnings.filterwarnings("ignore")
import yfinance as yf
from config import ALL_TICKERS, PORTFOLIO_TICKERS

failed = []
print(f"yfinance {yf.__version__}")
print(f"{'ticker':16} {'set':9} {'rows(30d)':>9} {'first':>11} {'last':>11} {'last_close':>11}  longName")
for t in ALL_TICKERS:
    h = yf.Ticker(t).history(period="30d")
    if h.empty:
        failed.append(t)
        print(f"{t:16} {'FAIL':9} no data")
        continue
    try:
        name = yf.Ticker(t).info.get("longName")
    except Exception as e:  # info endpoint is flakier than history
        name = f"<info error: {e}>"
    s = "portfolio" if t in PORTFOLIO_TICKERS else "ad-hoc"
    print(f"{t:16} {s:9} {len(h):>9} {h.index[0].date()!s:>11} {h.index[-1].date()!s:>11} {h['Close'].iloc[-1]:>11.2f}  {name}")

print(f"\n{len(ALL_TICKERS) - len(failed)}/{len(ALL_TICKERS)} OK" + (f"; FAILED: {failed}" if failed else ""))
sys.exit(1 if failed else 0)
