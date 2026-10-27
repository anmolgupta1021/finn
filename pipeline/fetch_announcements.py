"""
FINN Pipeline — Slice 2 & 4: Fetch, classify, and enrich NSE corporate announcements.

Primary source: NSE Corporate Announcements API (`www.nseindia.com/api/corporate-announcements`)
using `curl_cffi` browser impersonation (since BSE `api.bseindia.com` blocks automated
requests with Akamai 403).

Workflow per ticker:
1. Fetch recent announcements from NSE (`from_date` to `to_date`).
2. Preserve already-verified Slice 1 `results` extractions (matched by PDF URL).
3. Batch-classify remaining announcements via `gemini-3.5-flash-lite` into our
   17 categories + priority (`1` Material, `2` Notable, `3` Routine/Noise) +
   concise 1-line "so what?" summary grounded strictly in the NSE filing text.
4. For `management_change` filings with a PDF attachment, download the PDF, extract
   the statutory Brief Profile / Annexure text via `pdfplumber`, and extract
   `person_name`, `role`, `action`, and `background` (citing the filing page).
5. Save to `data/announcements/{SYMBOL}.json`.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pdfplumber
from curl_cffi import requests as creq

from config import (
    ANNOUNCEMENT_CATEGORIES,
    ANN_DIR,
    CATEGORY_PRIORITY,
    DOCS_DIR,
    PORTFOLIO_TICKERS,
    save_json,
    ticker_symbol,
)
from extract_results import call_gemini_multimodal, extract_results_from_pdf


FILINGS_DIR = DOCS_DIR / "filings"
RESULTS_DIR = DOCS_DIR / "results"
FILINGS_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def create_nse_session() -> creq.Session:
    """Create a curl_cffi Chrome-impersonated session with NSE cookies warmed up."""
    s = creq.Session(impersonate="chrome")
    s.get(
        "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
        timeout=15,
    )
    return s


def parse_nse_timestamp(raw_dt: str) -> str:
    """
    Convert NSE's '27-Oct-2026 11:45:12' or '17-Oct-2026 15:21:44' into
    ISO-8601 with IST offset ('2026-10-27T11:45:12+05:30').
    """
    if not raw_dt:
        return datetime.now().strftime("%Y-%m-%dT%H:%M:%S+05:30")
    for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M", "%d-%b-%Y"):
        try:
            dt = datetime.strptime(raw_dt.strip(), fmt)
            return dt.strftime("%Y-%m-%dT%H:%M:%S+05:30")
        except ValueError:
            continue
    return raw_dt


def fetch_nse_announcements_for_ticker(
    session: creq.Session,
    ticker: str,
    days_back: int = 30,
) -> list[dict[str, Any]]:
    """Fetch corporate announcements from NSE for a single ticker."""
    sym = ticker_symbol(ticker)
    to_dt = datetime.now()
    from_dt = to_dt - timedelta(days=days_back)
    url = (
        f"https://www.nseindia.com/api/corporate-announcements"
        f"?index=equities&symbol={sym}"
        f"&from_date={from_dt.strftime('%d-%m-%Y')}"
        f"&to_date={to_dt.strftime('%d-%m-%Y')}"
    )
    try:
        resp = session.get(url, timeout=20)
        if resp.status_code != 200:
            print(f"  ⚠️ NSE HTTP {resp.status_code} for {ticker}")
            return []
        data = resp.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        print(f"  ❌ NSE error for {ticker}: {e}")
        return []


CLASSIFICATION_PROMPT = """You are a senior Indian equity research analyst triaging NSE corporate announcements for a portfolio manager's morning briefing.

Classify each announcement for {ticker} ({company}) into:
1. `"category"`: MUST be one of:
   `["results", "M&A", "fund_raise", "management_change", "litigation", "insider_trading", "earnings_call", "investor_meetings", "credit_rating", "dividend", "bonus_split", "capex", "press_release", "postal_ballot", "agm_egm", "pledging", "unclassified"]`
   - Note: Loss/issue of duplicate share certificates, newspaper advertisements, investor grievances, or ESOP allotments of routine shares should be `"unclassified"` with `"priority": 3`.
   - Note: Appointment, re-appointment, resignation, or retirement of a Director, CEO, MD, CFO, Company Secretary, or Senior Management is `"management_change"`.
   - Note: Tax orders, show-cause notices, GST/customs penalties, or court/regulatory orders are `"litigation"`.
2. `"priority"`:
   - `1` (Material — "WHAT MATTERS"): Quarterly financial results outcomes, M&A/acquisitions/divestitures, CEO/MD/CFO/Board appointments or resignations, material capex/order wins, dividends/buybacks, large regulatory/tax orders (`> ₹10 Cr`).
   - `2` (Notable — "NOTABLE"): Earnings call intimations/transcripts, credit rating affirmations, press releases/business updates, small routine tax/GST penalty orders (`< ₹10 Cr`), postal ballots.
   - `3` (Routine / Noise — "NOISE"): Analyst/investor meet schedules, loss of share certificates, newspaper clippings, routine compliance disclosures under Reg 30/74(5).
3. `"summary"`: A sharp, factual 1-line "so what?" summary grounded ONLY in the provided NSE subject (`desc`) and text (`attchmntText`). Do NOT invent numbers, names, or facts not present in the text. No filler words.

Announcements to classify:
{items_json}

Return ONLY valid JSON matching this schema:
{{
  "classifications": [
    {{
      "index": 0,
      "category": "string",
      "priority": 1 | 2 | 3,
      "summary": "string"
    }}
  ]
}}
"""


MGMT_PROMPT = """You are extracting structured details from an Indian listed company's NSE filing regarding a change in Board of Directors / Key Managerial Personnel / Senior Management for {company} ({ticker}).

Read the filing text below and extract ONLY facts explicitly stated in the filing:
- If the filing announces a leadership transition (both an outgoing person and an incoming person assuming charge), prioritise the **incoming** person in `"person_name"` (`"action": "joined"`) and mention the outgoing person they succeeded in `"background"` and `"summary"`.
- `"person_name"`: Full name of the incoming person (or the departing person if only a resignation/cessation is announced).
- `"role"`: Exact designation / role (e.g. `"Managing Director and Chief Executive Officer"`, `"Independent Director"`).
- `"action"`: One of `"joined"` (for appointment / re-appointment / assuming charge), `"resigned"`, or `"retired"` (for completion of tenure / cessation when no successor is named in the same notice).
- `"background"`: 1–2 concise sentences summarising their background, qualifications, prior roles, or transition details strictly from the filing text, ending with `(Filing p. 1)` or the relevant page number.
- `"summary"`: A sharp 1-line headline summary for the morning briefing card (e.g., `"Anup Bagchi assumed charge as MD & CEO effective Oct 27, 2026, succeeding Sashidhar Jagdishan upon completion of his tenure."`).

Filing headline: {headline}
Filing text (by page):
\"\"\"
{pdf_text}
\"\"\"

Return ONLY valid JSON:
{{
  "person_name": "string",
  "role": "string",
  "action": "joined" | "resigned" | "retired",
  "background": "string",
  "summary": "string"
}}
"""


def enrich_management_change(
    session: creq.Session,
    ticker: str,
    company: str,
    headline: str,
    pdf_url: str,
    fallback_text: str,
) -> tuple[dict[str, Any], str | None, str, dict[str, int]]:
    """
    Download the management change PDF (if available), read its pages via
    pdfplumber, and extract person_name, role, action, and background.
    """
    pages_text = ""
    if pdf_url and pdf_url.lower().endswith(".pdf"):
        fname = pdf_url.split("/")[-1]
        local_path = FILINGS_DIR / fname
        if not local_path.exists():
            try:
                r = session.get(pdf_url, timeout=20)
                if r.status_code == 200 and r.content[:4] == b"%PDF":
                    local_path.write_bytes(r.content)
            except Exception:
                pass
        if local_path.exists():
            try:
                with pdfplumber.open(local_path) as pdf:
                    chunks = []
                    for idx, page in enumerate(pdf.pages[:5]):
                        t = (page.extract_text() or "").strip()
                        if t:
                            chunks.append(f"--- PAGE {idx + 1} ---\n{t}")
                    pages_text = "\n\n".join(chunks)
            except Exception:
                pages_text = ""

    if not pages_text:
        pages_text = f"--- NSE FILING TEXT ---\n{fallback_text}"

    prompt = MGMT_PROMPT.format(
        company=company,
        ticker=ticker,
        headline=headline,
        pdf_text=pages_text[:8000],
    )
    out, model_used, t_in, t_out = call_gemini_multimodal(
        prompt=prompt,
        image_png_bytes=None,
        task="enrich_mgmt_v2",
        ticker=ticker,
    )
    enrichment = {
        "person_name": out.get("person_name"),
        "role": out.get("role"),
        "action": out.get("action", "joined"),
        "background": out.get("background"),
    }
    new_summary = out.get("summary") or fallback_text
    return enrichment, new_summary, model_used, {"in": t_in, "out": t_out}


def select_representative_nse_rows(
    raw_rows: list[dict[str, Any]],
    max_items: int = 6,
) -> list[dict[str, Any]]:
    """
    Deduplicate NSE rows by attachment URL / text and select up to `max_items`
    per ticker, prioritising non-routine filings + the most recent filings so
    24h/14d/30d windows show both high-signal items and collapsed routine noise.
    """
    seen_keys: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for r in raw_rows:
        pdf_url = (r.get("attchmntFile") or "").strip()
        if pdf_url.lower().endswith(".xml"):
            # Skip duplicate XBRL XML rows when NSE already provides the PDF row
            continue
        desc = (r.get("desc") or "").strip()
        txt = (r.get("attchmntText") or "").strip()
        dt = (r.get("an_dt") or "").strip()
        key = pdf_url if pdf_url else f"{desc}|{txt}|{dt}"
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(r)

    # Score rows so material subjects (Outcome of Board Meeting, Appointment,
    # Cessation, Acquisition, Press Release, Dividend, Order) are never crowded
    # out by 20 "Loss of Share Certificates" notices.
    def _row_priority_hint(r: dict[str, Any]) -> int:
        d = ((r.get("desc") or "") + " " + (r.get("attchmntText") or "")).lower()
        if any(
            k in d
            for k in [
                "outcome of board meeting",
                "financial results",
                "appointment",
                "cessation",
                "resignation",
                "acquisition",
                "amalgamation",
                "merger",
                "dividend",
                "buyback",
                "press release",
                "media release",
                "credit rating",
            ]
        ):
            return 0
        if "loss of share" in d or "duplicate share" in d or "newspaper" in d:
            return 2
        return 1

    # Always keep the 2 most recent filings (for 24h freshness) + top priority filings
    recent_two = deduped[:2]
    rest = sorted(deduped[2:], key=_row_priority_hint)
    combined = recent_two + rest
    return combined[:max_items]


def process_ticker_announcements(
    session: creq.Session,
    ticker: str,
    days_back: int = 30,
) -> list[dict[str, Any]]:
    sym = ticker_symbol(ticker)
    ann_path = ANN_DIR / f"{sym}.json"

    # Load existing announcements so we preserve verified Slice 1 results extractions
    existing_by_url: dict[str, dict[str, Any]] = {}
    existing_results: list[dict[str, Any]] = []
    if ann_path.exists():
        try:
            for a in json.loads(ann_path.read_text()):
                if a.get("category") == "results" and a.get("enrichment"):
                    if a.get("source_url"):
                        existing_by_url[a["source_url"]] = a
                    existing_results.append(a)
        except Exception:
            pass

    raw_rows = fetch_nse_announcements_for_ticker(session, ticker, days_back=days_back)
    selected_rows = select_representative_nse_rows(raw_rows, max_items=6)

    to_classify: list[dict[str, Any]] = []
    preserved: list[dict[str, Any]] = list(existing_results)
    preserved_urls = {a.get("source_url") for a in preserved if a.get("source_url")}

    for r in selected_rows:
        pdf_url = (r.get("attchmntFile") or "").strip()
        if pdf_url and pdf_url in preserved_urls:
            continue
        to_classify.append(r)

    if not to_classify:
        save_json(ann_path, preserved)
        return preserved

    company_name = (
        to_classify[0].get("sm_name")
        or (preserved[0].get("company_name") if preserved else sym)
    )

    items_payload = [
        {
            "index": idx,
            "date": r.get("an_dt", ""),
            "subject": r.get("desc", ""),
            "details": (r.get("attchmntText") or "")[:500],
        }
        for idx, r in enumerate(to_classify)
    ]

    prompt = CLASSIFICATION_PROMPT.format(
        ticker=ticker,
        company=company_name,
        items_json=json.dumps(items_payload, indent=2),
    )
    llm_out, model_used, t_in, t_out = call_gemini_multimodal(
        prompt=prompt,
        image_png_bytes=None,
        task="classify_nse_v1",
        ticker=ticker,
    )
    classifications = {
        int(c["index"]): c
        for c in (llm_out.get("classifications") or [])
        if isinstance(c, dict) and "index" in c
    }

    per_item_in = max(1, t_in // len(to_classify))
    per_item_out = max(1, t_out // len(to_classify))

    final_anns: list[dict[str, Any]] = list(preserved)
    for idx, r in enumerate(to_classify):
        c = classifications.get(idx, {})
        cat = c.get("category", "unclassified")
        if cat not in ANNOUNCEMENT_CATEGORIES:
            cat = "unclassified"
        prio = int(c.get("priority") or CATEGORY_PRIORITY.get(cat, 3))
        if prio not in (1, 2, 3):
            prio = 3

        pdf_url = (r.get("attchmntFile") or "").strip()
        raw_dt = (r.get("an_dt") or "").strip()
        iso_ts = parse_nse_timestamp(raw_dt)
        desc = (r.get("desc") or "Filing").strip()
        att_text = (r.get("attchmntText") or "").strip()
        headline = f"{desc} — {att_text}" if att_text and att_text != desc else desc
        summary = c.get("summary") or att_text or desc

        uid_seed = f"{ticker}|{raw_dt}|{pdf_url or headline}"
        ann_id = f"nse-{sym.lower()}-{hashlib.sha256(uid_seed.encode()).hexdigest()[:10]}"

        enrichment: dict[str, Any] = {}
        item_model = model_used
        item_tokens = {"in": per_item_in, "out": per_item_out}

        if cat == "results" and not enrichment and preserved:
            cat = "unclassified"
            prio = 3

        # Enrich management_change filings from the actual PDF attachment
        if cat == "management_change":
            try:
                enrichment, mgmt_summary, m_model, m_tok = enrich_management_change(
                    session=session,
                    ticker=ticker,
                    company=company_name,
                    headline=headline,
                    pdf_url=pdf_url,
                    fallback_text=att_text or desc,
                )
                if mgmt_summary:
                    summary = mgmt_summary
                item_model = m_model
                item_tokens = {
                    "in": per_item_in + m_tok["in"],
                    "out": per_item_out + m_tok["out"],
                }
            except Exception as e:
                print(f"  ⚠️ Management enrichment failed for {ticker}: {e}")

        final_anns.append(
            {
                "id": ann_id,
                "ticker": ticker,
                "company_name": company_name,
                "timestamp": iso_ts,
                "headline": headline[:280],
                "category": cat,
                "priority": prio,
                "summary": summary,
                "source_url": pdf_url,
                "raw_text": att_text or desc,
                "enrichment": enrichment,
                "model_used": item_model,
                "tokens": item_tokens,
            }
        )

    # Sort by timestamp descending
    final_anns.sort(key=lambda a: a.get("timestamp", ""), reverse=True)
    save_json(ann_path, final_anns)
    return final_anns


if __name__ == "__main__":
    print("=" * 64)
    print("FINN — Fetching, classifying & enriching NSE announcements")
    print("=" * 64)
    sess = create_nse_session()
    total_count = 0
    for t in PORTFOLIO_TICKERS:
        print(f"\n📋 {t}...")
        anns = process_ticker_announcements(sess, t, days_back=30)
        total_count += len(anns)
        p1 = sum(1 for a in anns if a["priority"] == 1)
        p2 = sum(1 for a in anns if a["priority"] == 2)
        p3 = sum(1 for a in anns if a["priority"] == 3)
        print(f"  ✅ {len(anns)} total ({p1} material, {p2} notable, {p3} routine)")
        time.sleep(0.4)
    print(f"\nDone. {total_count} announcements across {len(PORTFOLIO_TICKERS)} portfolio stocks.")
