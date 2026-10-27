"""
FINN Pipeline — Shared configuration and utilities.

All pipeline scripts import from here for consistent paths, tickers, and helpers.
"""

import os
import json
import hashlib
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional, List, Dict

# ─── Paths ───────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
PRICES_DIR = DATA_DIR / "prices"
ANN_DIR = DATA_DIR / "announcements"
RESEARCH_DIR = DATA_DIR / "research"
DOCS_DIR = DATA_DIR / "documents"
LLM_LOG = DATA_DIR / "llm_log.json"

for d in [PRICES_DIR, ANN_DIR, RESEARCH_DIR, DOCS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ─── Portfolio ───────────────────────────────────────────────────────────────
PORTFOLIO_TICKERS = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "HINDUNILVR.NS", "BHARTIARTL.NS", "LT.NS", "TATAMOTORS.NS", "SUNPHARMA.NS",
    "MARUTI.NS", "TITAN.NS", "ASIANPAINT.NS", "TATASTEEL.NS", "NTPC.NS",
]

ADHOC_TICKERS = ["BAJFINANCE.NS", "ZOMATO.NS", "ITC.NS"]

ALL_TICKERS = PORTFOLIO_TICKERS + ADHOC_TICKERS

# Ticker → BSE scrip code mapping (needed for BSE API)
# Will be populated by fetch_announcements.py
TICKER_TO_BSE = {}

# ─── Announcement categories (from reference doc) ───────────────────────────
ANNOUNCEMENT_CATEGORIES = [
    "results", "M&A", "fund_raise", "management_change", "litigation",
    "insider_trading", "earnings_call", "investor_meetings", "credit_rating",
    "dividend", "bonus_split", "capex", "press_release", "postal_ballot",
    "agm_egm", "pledging", "unclassified",
]

# Priority mapping: category → default priority (1=high, 2=medium, 3=routine)
CATEGORY_PRIORITY = {
    "results": 1, "M&A": 1, "management_change": 1, "litigation": 1,
    "insider_trading": 1, "fund_raise": 2, "earnings_call": 2,
    "credit_rating": 2, "capex": 2, "dividend": 2, "bonus_split": 2,
    "press_release": 2, "investor_meetings": 3, "postal_ballot": 3,
    "agm_egm": 3, "pledging": 2, "unclassified": 3,
}


# ─── LLM call logging ───────────────────────────────────────────────────────
def content_hash(text: str) -> str:
    """SHA-256 hash of content for cache key."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def log_llm_call(
    task: str,
    ticker: str,
    model: str,
    tokens_in: int,
    tokens_out: int,
    chash: str,
    cache_hit: bool,
) -> None:
    """Append an LLM call record to the cost log."""
    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "task": task,
        "ticker": ticker,
        "model": model,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "content_hash": chash,
        "cache_hit": cache_hit,
        "cost_usd": 0.00,  # Free tier
    }
    log = []
    if LLM_LOG.exists():
        log = json.loads(LLM_LOG.read_text())
    log.append(entry)
    LLM_LOG.write_text(json.dumps(log, indent=2))


# ─── LLM cache ──────────────────────────────────────────────────────────────
CACHE_DIR = DATA_DIR / ".llm_cache"
CACHE_DIR.mkdir(exist_ok=True)


def get_cached(chash: str, task: str) -> Optional[dict]:
    """Return cached LLM output if it exists."""
    cache_file = CACHE_DIR / f"{task}_{chash}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())
    return None


def set_cache(chash: str, task: str, result: dict) -> None:
    """Cache an LLM output by content hash + task."""
    cache_file = CACHE_DIR / f"{task}_{chash}.json"
    cache_file.write_text(json.dumps(result, indent=2))


# ─── JSON helpers ────────────────────────────────────────────────────────────
def save_json(path: Path, data: Any) -> None:
    """Write data to a JSON file with pretty-printing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str))
    print(f"  💾 Saved {path.relative_to(ROOT)}")


def load_json(path: Path) -> Any:
    """Load data from a JSON file."""
    return json.loads(path.read_text())


def ticker_symbol(ticker: str) -> str:
    """RELIANCE.NS → RELIANCE"""
    return ticker.split(".")[0]
