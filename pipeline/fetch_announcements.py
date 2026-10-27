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
    DATA_DIR,
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


def dedup_nse_rows(raw_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Remove only duplicate XBRL `.xml` rows and exact duplicate URL+timestamp rows.
    NO `max_items` cap — ingests 100% of unique announcements returned by NSE.
    """
    seen_keys: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for r in raw_rows:
        pdf_url = (r.get("attchmntFile") or "").strip()
        if pdf_url.lower().endswith(".xml"):
            continue
        desc = (r.get("desc") or "").strip()
        txt = (r.get("attchmntText") or "").strip()
        dt = (r.get("an_dt") or "").strip()
        key = f"{pdf_url}|{dt}" if pdf_url else f"{desc}|{txt}|{dt}"
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(r)
    return deduped


def classify_by_rules(desc: str, att_text: str) -> tuple[str, int, str] | None:
    """
    Deterministic rule-first classifier from NSE `desc` (subject) and `attchmntText`.
    Returns `(category, priority, summary)` when unambiguous, or `None` when ambiguous
    so the LLM is invoked only for ambiguous cases and P1/P2 enrichment.
    """
    d_low = desc.lower().strip()
    t_low = att_text.lower().strip()
    combined = f"{d_low} {t_low}"

    # 1. P3 Routine / Noise (deterministic, 0 LLM calls)
    if any(k in combined for k in ["loss of share", "duplicate share", "issue of duplicate", "lost share"]):
        return ("unclassified", 3, att_text or desc)
    if any(k in combined for k in ["newspaper publication", "newspaper advertisement", "newspaper clipping", "copy of newspaper"]):
        return ("unclassified", 3, att_text or desc)
    if d_low in ("esop/esos/esps", "allotment of equity shares", "allotment of shares") or (
        "esop" in combined or "esos" in combined or "employee stock option" in combined
    ):
        return ("unclassified", 3, att_text or desc)
    if "certificate under sebi (depositories and participants)" in combined or "regulation 74(5)" in combined or "reg. 74(5)" in combined or "reg 74(5)" in combined:
        return ("unclassified", 3, att_text or desc)
    if "trading window" in combined:
        return ("insider_trading", 3, att_text or desc)
    if d_low == "shareholders meeting" or any(k in combined for k in ["scrutinizer", "voting results", "annual general meeting", "extraordinary general meeting"]):
        return ("agm_egm", 3, att_text or desc)

    # 2. Investor meets vs Earnings Call transcripts/recordings
    if "analysts/institutional investor meet" in d_low or "con. call updates" in d_low or "investor meet" in d_low:
        if any(k in combined for k in ["transcript", "audio recording", "link of recording", "video recording", "earnings call"]):
            return ("earnings_call", 2, att_text or desc)
        return ("investor_meetings", 3, att_text or desc)

    # 3. P2 Notable categories with clear NSE subject labels
    if "postal ballot" in d_low:
        return ("postal_ballot", 2, att_text or desc)
    if "credit rating" in d_low:
        return ("credit_rating", 2, att_text or desc)
    if d_low in ("press release", "media release", "press release / media release"):
        return ("press_release", 2, att_text or desc)

    # 4. P1 Material categories with clear NSE subject labels
    if d_low in ("change in director(s)", "change in management", "change in directors/ key managerial personnel") or any(
        k in d_low for k in ["appointment", "cessation", "resignation", "demise"]
    ):
        return ("management_change", 1, att_text or desc)
    if "dividend" in d_low:
        return ("dividend", 1, att_text or desc)
    if any(k in d_low for k in ["acquisition", "amalgamation", "merger", "scheme of arrangement", "joint venture", "sale or disposal"]):
        return ("M&A", 1, att_text or desc)
    if any(k in d_low for k in ["buyback", "bonus", "split", "sub-division"]):
        return ("bonus_split", 1, att_text or desc)
    if any(k in d_low for k in ["fund raising", "qualified institutional placement"]):
        return ("fund_raise", 1, att_text or desc)
    if "outcome of board meeting" in d_low or "financial results" in d_low:
        if "financial results" in combined or "unaudited" in combined or "audited" in combined:
            return ("results", 1, att_text or desc)

    # Ambiguous (e.g., "General Updates", "Updates", "Order", etc.) -> send to LLM
    return None


def _load_slice1_by_url_and_ticker() -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    s1_path = DATA_DIR / "slice1_extractions.json"
    by_url: dict[str, dict[str, Any]] = {}
    by_ticker: dict[str, dict[str, Any]] = {}
    if s1_path.exists():
        try:
            for item in json.loads(s1_path.read_text()):
                if item.get("source_url"):
                    by_url[item["source_url"]] = item
                if item.get("ticker"):
                    by_ticker[item["ticker"]] = item
        except Exception:
            pass
    return by_url, by_ticker


def _build_slice1_enrichment(s1: dict[str, Any]) -> tuple[dict[str, Any], str, str | None, dict[str, int]]:
    if s1.get("status") != "ok":
        enrichment = {
            "status": s1.get("status", "corrupted_pdf"),
            "quarter": s1.get("quarter", "Q2 FY27"),
            "error": s1.get("error", "Filing couldn't be read, open original"),
            "highlights": s1.get("highlights", "Filing couldn't be read, open original"),
        }
        summary = f"{s1.get('quarter', 'Q2 FY27')} Financial Results — Filing couldn't be read, open original"
        return enrichment, summary, None, {"in": 0, "out": 0}

    enrichment = {
        "status": "ok",
        "quarter": s1.get("quarter"),
        "basis": s1.get("basis"),
        "entity_type": s1.get("entity_type"),
        "reported_unit": s1.get("reported_unit"),
        "normalised_unit": s1.get("normalised_unit"),
        "source_page": s1.get("source_page"),
        "vision_used": s1.get("vision_used"),
        "ebitda_status": s1.get("ebitda_status"),
        "revenue_label": s1.get("revenue_label"),
        "period_ended": s1.get("period_ended"),
        "revenue": s1.get("revenue"),
        "ebitda": s1.get("ebitda"),
        "operating_profit_ex_provisions": s1.get("operating_profit_ex_provisions"),
        "pbt": s1.get("pbt"),
        "pat": s1.get("pat"),
        "pat_owners": s1.get("pat_owners"),
        "derivation": s1.get("derivation"),
        "validation": s1.get("validation"),
        "highlights": s1.get("highlights"),
    }
    return (
        enrichment,
        s1.get("summary") or "Quarterly financial results",
        s1.get("model_used"),
        s1.get("tokens") or {"in": 0, "out": 0},
    )


def process_ticker_announcements(
    session: creq.Session,
    ticker: str,
    days_back: int = 30,
    stats_accum: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    sym = ticker_symbol(ticker)
    ann_path = ANN_DIR / f"{sym}.json"
    s1_by_url, s1_by_ticker = _load_slice1_by_url_and_ticker()

    # Preserve off-window Slice 1 Q1 FY27 results cards (RELIANCE, SUNPHARMA, MARUTI, ITC, PAGEIND)
    # while ingesting 100% of the 30-day NSE window announcements without any cap.
    raw_rows = fetch_nse_announcements_for_ticker(session, ticker, days_back=days_back)
    all_rows = dedup_nse_rows(raw_rows)

    company_name = (
        (all_rows[0].get("sm_name") if all_rows else None)
        or (s1_by_ticker.get(ticker, {}).get("company_name"))
        or sym
    )

    rule_classified: dict[int, tuple[str, int, str]] = {}
    ambiguous_indices: list[int] = []

    for idx, r in enumerate(all_rows):
        desc = (r.get("desc") or "Filing").strip()
        att_text = (r.get("attchmntText") or "").strip()
        res = classify_by_rules(desc, att_text)
        if res is not None:
            rule_classified[idx] = res
        else:
            ambiguous_indices.append(idx)

    llm_classifications: dict[int, dict[str, Any]] = {}
    llm_model_used: str | None = None
    per_ambig_in = 0
    per_ambig_out = 0
    batch_llm_calls = 0

    if ambiguous_indices:
        items_payload = [
            {
                "index": idx,
                "date": all_rows[idx].get("an_dt", ""),
                "subject": all_rows[idx].get("desc", ""),
                "details": (all_rows[idx].get("attchmntText") or "")[:500],
            }
            for idx in ambiguous_indices
        ]
        prompt = CLASSIFICATION_PROMPT.format(
            ticker=ticker,
            company=company_name,
            items_json=json.dumps(items_payload, indent=2),
        )
        llm_out, llm_model_used, t_in, t_out = call_gemini_multimodal(
            prompt=prompt,
            image_png_bytes=None,
            task="classify_nse_v1",
            ticker=ticker,
        )
        batch_llm_calls = 1
        llm_classifications = {
            int(c["index"]): c
            for c in (llm_out.get("classifications") or [])
            if isinstance(c, dict) and "index" in c
        }
        per_ambig_in = max(1, t_in // len(ambiguous_indices))
        per_ambig_out = max(1, t_out // len(ambiguous_indices))

    final_anns: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    mgmt_enrichment_calls = 0

    for idx, r in enumerate(all_rows):
        pdf_url = (r.get("attchmntFile") or "").strip()
        if pdf_url:
            seen_urls.add(pdf_url)
        raw_dt = (r.get("an_dt") or "").strip()
        iso_ts = parse_nse_timestamp(raw_dt)
        desc = (r.get("desc") or "Filing").strip()
        att_text = (r.get("attchmntText") or "").strip()
        headline = f"{desc} — {att_text}" if att_text and att_text != desc else desc

        if idx in rule_classified:
            cat, prio, summary = rule_classified[idx]
            item_model: str | None = "rule_engine"
            item_tokens = {"in": 0, "out": 0}
        else:
            c = llm_classifications.get(idx, {})
            cat = c.get("category", "unclassified")
            if cat not in ANNOUNCEMENT_CATEGORIES:
                cat = "unclassified"
            prio = int(c.get("priority") or CATEGORY_PRIORITY.get(cat, 3))
            if prio not in (1, 2, 3):
                prio = 3
            summary = c.get("summary") or att_text or desc
            item_model = llm_model_used
            item_tokens = {"in": per_ambig_in, "out": per_ambig_out}

        uid_seed = f"{ticker}|{raw_dt}|{pdf_url or headline}"
        ann_id = f"nse-{sym.lower()}-{hashlib.sha256(uid_seed.encode()).hexdigest()[:10]}"
        enrichment: dict[str, Any] = {}

        # Attach Slice 1 results extraction (or HDFCBANK corrupted_pdf fallback) if matched
        if pdf_url in s1_by_url or (cat == "results" and ticker in s1_by_ticker):
            s1_entry = s1_by_url.get(pdf_url) or s1_by_ticker[ticker]
            enrichment, s1_summary, s1_mod, s1_tok = _build_slice1_enrichment(s1_entry)
            cat = "results"
            prio = 1
            summary = s1_summary
            item_model = s1_mod
            item_tokens = s1_tok

        # Enrich management_change filings from the actual PDF attachment
        elif cat == "management_change":
            try:
                enrichment, mgmt_summary, m_model, m_tok = enrich_management_change(
                    session=session,
                    ticker=ticker,
                    company=company_name,
                    headline=headline,
                    pdf_url=pdf_url,
                    fallback_text=att_text or desc,
                )
                mgmt_enrichment_calls += 1
                if mgmt_summary:
                    summary = mgmt_summary
                item_model = m_model
                item_tokens = {
                    "in": item_tokens["in"] + m_tok["in"],
                    "out": item_tokens["out"] + m_tok["out"],
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

    # Also ensure Q1 FY27 Slice 1 results filings outside the 30d window remain available
    # for 14d/30d results inspection if not already in the 30d NSE response
    if ticker in s1_by_ticker:
        s1_entry = s1_by_ticker[ticker]
        s1_url = s1_entry.get("source_url", "")
        if s1_url and s1_url not in seen_urls and s1_entry.get("status") == "ok":
            # Keep existing timestamp from previous announcement file if present
            enrichment, s1_summary, s1_mod, s1_tok = _build_slice1_enrichment(s1_entry)
            p_end = (s1_entry.get("period_ended") or {}).get("current") or "2026-07-31"
            final_anns.append(
                {
                    "id": f"nse-{sym.lower()}-slice1-{s1_entry.get('quarter', 'q1fy27').lower().replace(' ', '')}",
                    "ticker": ticker,
                    "company_name": s1_entry.get("company_name", company_name),
                    "timestamp": f"{p_end}T16:00:00+05:30",
                    "headline": f"Outcome of Board Meeting — {s1_entry.get('quarter')} Financial Results ({s1_entry.get('basis', '').title()})",
                    "category": "results",
                    "priority": 1,
                    "summary": s1_summary,
                    "source_url": s1_url,
                    "raw_text": s1_summary,
                    "enrichment": enrichment,
                    "model_used": s1_mod,
                    "tokens": s1_tok,
                }
            )

    final_anns.sort(key=lambda a: a.get("timestamp", ""), reverse=True)
    save_json(ann_path, final_anns)

    if stats_accum is not None:
        stats_accum["per_ticker"][ticker] = {
            "nse_raw_30d": len(raw_rows),
            "nse_unique_non_xml_30d": len(all_rows),
            "stored_total": len(final_anns),
            "classified_by_rules": len(rule_classified),
            "classified_by_llm_ambiguous": len(ambiguous_indices),
            "batch_classify_llm_calls": batch_llm_calls,
            "mgmt_enrichment_llm_calls": mgmt_enrichment_calls,
        }
        stats_accum["total_nse_30d"] += len(all_rows)
        stats_accum["total_stored"] += len(final_anns)
        stats_accum["total_classified_by_rules"] += len(rule_classified)
        stats_accum["total_classified_by_llm"] += len(ambiguous_indices)
        stats_accum["total_batch_classify_llm_calls"] += batch_llm_calls
        stats_accum["total_mgmt_enrichment_llm_calls"] += mgmt_enrichment_calls

    return final_anns


if __name__ == "__main__":
    print("=" * 64)
    print("FINN — Fetching, classifying & enriching ALL NSE announcements")
    print("=" * 64)
    sess = create_nse_session()
    stats: dict[str, Any] = {
        "total_nse_30d": 0,
        "total_stored": 0,
        "total_classified_by_rules": 0,
        "total_classified_by_llm": 0,
        "total_batch_classify_llm_calls": 0,
        "total_mgmt_enrichment_llm_calls": 0,
        "per_ticker": {},
    }
    for t in PORTFOLIO_TICKERS:
        print(f"\n📋 {t}...")
        anns = process_ticker_announcements(sess, t, days_back=30, stats_accum=stats)
        p1 = sum(1 for a in anns if a["priority"] == 1)
        p2 = sum(1 for a in anns if a["priority"] == 2)
        p3 = sum(1 for a in anns if a["priority"] == 3)
        tk_stat = stats["per_ticker"][t]
        print(
            f"  ✅ {len(anns)} stored (30d NSE={tk_stat['nse_unique_non_xml_30d']}, "
            f"rules={tk_stat['classified_by_rules']}, llm_ambig={tk_stat['classified_by_llm_ambiguous']} | "
            f"{p1} P1, {p2} P2, {p3} P3)"
        )
        time.sleep(0.3)

    # Calculate LLM calls saved:
    #- Per-item LLM call baseline: total_nse_30d calls vs (total_batch_classify_llm_calls + total_mgmt_enrichment_llm_calls)
    # - Items classified without LLM: total_classified_by_rules out of total_nse_30d
    stats["items_saved_from_llm_classification"] = stats["total_classified_by_rules"]
    stats["pct_items_classified_by_rules"] = round(
        100.0 * stats["total_classified_by_rules"] / max(1, stats["total_nse_30d"]), 2
    )
    stats["per_item_llm_calls_avoided"] = (
        stats["total_nse_30d"] - stats["total_batch_classify_llm_calls"]
    )
    save_json(DATA_DIR / "announcement_ingestion_stats.json", stats)
    print("\n" + "=" * 64)
    print(
        f"Done. {stats['total_stored']} stored ({stats['total_nse_30d']} 30d NSE filings: "
        f"{stats['total_classified_by_rules']} via rules [{stats['pct_items_classified_by_rules']}%], "
        f"{stats['total_classified_by_llm']} ambiguous via {stats['total_batch_classify_llm_calls']} batched LLM calls, "
        f"{stats['total_mgmt_enrichment_llm_calls']} P1 management PDF enrichment calls)."
    )
