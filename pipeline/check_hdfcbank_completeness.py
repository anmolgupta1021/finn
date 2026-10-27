"""
Step 4: Completeness check for HDFCBANK.NS over 30 days against live NSE API.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from config import ANN_DIR, DATA_DIR, save_json
from fetch_announcements import (
    create_nse_session,
    fetch_nse_announcements_for_ticker,
    select_representative_nse_rows,
)


def main() -> None:
    session = create_nse_session()
    days_back = 30
    to_dt = datetime.now()
    from_dt = to_dt - timedelta(days=days_back)

    raw_rows = fetch_nse_announcements_for_ticker(session, "HDFCBANK.NS", days_back=days_back)

    # Break down the raw NSE API response
    xml_rows = [r for r in raw_rows if (r.get("attchmntFile") or "").lower().endswith(".xml")]
    non_xml_rows = [r for r in raw_rows if not (r.get("attchmntFile") or "").lower().endswith(".xml")]

    seen_keys = set()
    deduped_non_xml = []
    for r in non_xml_rows:
        pdf_url = (r.get("attchmntFile") or "").strip()
        desc = (r.get("desc") or "").strip()
        txt = (r.get("attchmntText") or "").strip()
        dt = (r.get("an_dt") or "").strip()
        key = pdf_url if pdf_url else f"{desc}|{txt}|{dt}"
        if key not in seen_keys:
            seen_keys.add(key)
            deduped_non_xml.append(r)

    capped_rows = select_representative_nse_rows(raw_rows, max_items=6)

    saved_file = ANN_DIR / "HDFCBANK.json"
    saved_rows = json.loads(saved_file.read_text()) if saved_file.exists() else []

    by_desc: dict[str, int] = {}
    for r in raw_rows:
        d = (r.get("desc") or "Unknown").strip()
        by_desc[d] = by_desc.get(d, 0) + 1

    report = {
        "ticker": "HDFCBANK.NS",
        "window_days": days_back,
        "from_date": from_dt.strftime("%d-%m-%Y"),
        "to_date": to_dt.strftime("%d-%m-%Y"),
        "nse_endpoint": (
            f"https://www.nseindia.com/api/corporate-announcements"
            f"?index=equities&symbol=HDFCBANK"
            f"&from_date={from_dt.strftime('%d-%m-%Y')}&to_date={to_dt.strftime('%d-%m-%Y')}"
        ),
        "is_nse_api_paginated": False,
        "nse_pagination_explanation": (
            "NSE's /api/corporate-announcements endpoint is NOT paginated when queried with "
            "symbol + from_date + to_date; it returns the complete JSON array of all corporate "
            "announcements filed in that window in a single HTTP response."
        ),
        "is_our_pipeline_capped": True,
        "our_pipeline_cap_explanation": (
            "Our pipeline (fetch_announcements.py -> select_representative_nse_rows) intentionally "
            "filters out duplicate XBRL .xml attachments, deduplicates by PDF URL, and caps LLM "
            "classification at max_items=6 per ticker (keeping the 2 newest filings + highest-priority "
            "material filings like Outcome of Board Meeting, Appointment/Cessation, Press Release, "
            "Dividend/Ratings while dropping repetitive 'Loss of Share Certificates' and daily ESOP "
            "allotment noise)."
        ),
        "counts": {
            "nse_raw_total_30d": len(raw_rows),
            "nse_xml_xbrl_duplicates": len(xml_rows),
            "nse_non_xml_filings": len(non_xml_rows),
            "nse_unique_pdf_filings": len(deduped_non_xml),
            "pipeline_capped_for_llm_triage": len(capped_rows),
            "saved_in_data_announcements_hdfcbank_json": len(saved_rows),
        },
        "nse_raw_breakdown_by_subject": by_desc,
        "all_nse_raw_filings_30d": [
            {
                "an_dt": r.get("an_dt"),
                "desc": r.get("desc"),
                "attchmntText": (r.get("attchmntText") or "")[:160],
                "attchmntFile": r.get("attchmntFile"),
            }
            for r in raw_rows
        ],
    }

    save_json(DATA_DIR / "hdfcbank_completeness_30d.json", report)
    print(json.dumps(report["counts"], indent=2))
    print("\nBreakdown by NSE subject (desc):")
    for k, v in sorted(by_desc.items(), key=lambda x: -x[1]):
        print(f"  {v:2d}x | {k}")


if __name__ == "__main__":
    main()
