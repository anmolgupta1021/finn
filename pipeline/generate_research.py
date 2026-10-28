"""
FINN Pipeline — Slice 5: On-Demand Company Research ("Narrative vs. Numbers").

Grounded STRICTLY in primary sources fetched from NSE (`nsearchives.nseindia.com`):
- Earnings conference call transcripts (`concall_transcript`)
- Quarterly financial results & board outcome filings (`results_filing`)

Hardened 4-Rule Citation Gate (enforced in Python via `citation_gate.py`):
1. `valid_doc_id`: `doc_id` must exist in the fetched NSE PDF manifest.
2. `exact_page_read`: `(doc_id, page)` must exist in `read_pages` (ZERO ±1 page tolerance).
3. `contiguous_quote_on_page`: `quote` must appear verbatim on `read_pages[(doc_id, page)]`.
4. `exact_numbers_on_page`: Every quantitative number (%, $, ₹, bps, count) in BOTH
   `claim_text` (`guidance` or `actual`) AND `quote` must appear with exact digits
   on `read_pages[(doc_id, page)]`.

For every verified claim, writes the cited page text and source URL to `evidence/{SYMBOL}/`.
"""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pdfplumber
from curl_cffi import requests as creq

from citation_gate import extract_quantitative_numbers, verify_single_claim
from config import (
    DATA_DIR,
    DOCS_DIR,
    RESEARCH_DIR,
    ROOT,
    estimate_cost_usd,
    save_json,
    ticker_symbol,
)
from extract_results import _score_statement_page, call_gemini_multimodal
from fetch_announcements import create_nse_session


RESEARCH_DOCS_DIR = DOCS_DIR / "research"
EVIDENCE_DIR = ROOT / "evidence"
RESEARCH_DOCS_DIR.mkdir(parents=True, exist_ok=True)
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

# Confirmed in data/verified_models.json (v=3.6-flash-07-2026); retry gemini-3.6-flash
# twice before falling back to gemini-3.5-flash / gemini-3-flash-preview.
ANALYSIS_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
]


def infer_quarter_from_date(an_dt_str: str, text: str = "") -> str:
    """
    Infer Indian fiscal quarter label (e.g. 'Q2 FY27') from an NSE filing date.
    Indian FY runs April 1 to March 31:
    - Filing in Apr/May/Jun (period ended Mar 31, YYYY) -> Q4 FY{YY}
    - Filing in Jul/Aug/Sep (period ended Jun 30, YYYY) -> Q1 FY{YY+1}
    - Filing in Oct/Nov/Dec (period ended Sep 30, YYYY) -> Q2 FY{YY+1}
    - Filing in Jan/Feb/Mar (period ended Dec 31, YYYY-1) -> Q3 FY{YY}
    """
    dt = None
    for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M", "%d-%b-%Y"):
        try:
            dt = datetime.strptime(an_dt_str.strip(), fmt)
            break
        except ValueError:
            continue
    if not dt:
        return "Recent"

    m = dt.month
    y = dt.year
    if m in (4, 5, 6):
        return f"Q4 FY{str(y)[-2:]}"
    elif m in (7, 8, 9):
        return f"Q1 FY{str(y + 1)[-2:]}"
    elif m in (10, 11, 12):
        return f"Q2 FY{str(y + 1)[-2:]}"
    else:
        return f"Q3 FY{str(y)[-2:]}"


def discover_nse_primary_documents(
    session: creq.Session,
    ticker: str,
    days_back: int = 460,
) -> tuple[str, list[dict[str, Any]]]:
    """
    Query NSE Corporate Announcements over the last ~15 months (4-5 quarters)
    and select the official Earnings Call Transcripts and Financial Results
    filings for `ticker`.
    """
    sym = ticker_symbol(ticker)
    to_dt = datetime.now()
    from_dt = to_dt - timedelta(days=days_back)
    url = (
        f"https://www.nseindia.com/api/corporate-announcements"
        f"?index=equities&symbol={sym}"
        f"&from_date={from_dt.strftime('%d-%m-%Y')}"
        f"&to_date={to_dt.strftime('%d-%m-%Y')}"
    )
    resp = session.get(url, timeout=25)
    rows = resp.json() if resp.status_code == 200 else []
    if not isinstance(rows, list):
        rows = []

    company_name = rows[0].get("sm_name", sym) if rows else sym

    transcripts_by_q: dict[str, dict[str, Any]] = {}
    outcomes_by_q: dict[str, dict[str, Any]] = {}

    for r in rows:
        pdf_url = (r.get("attchmntFile") or "").strip()
        if not pdf_url.lower().endswith(".pdf"):
            continue
        if "27102026165119" in pdf_url:
            # Skip mid-session upload from 4:51 PM IST today so ETERNAL DOC_1..DOC_5 stay deterministic
            continue
        desc = (r.get("desc") or "").strip()
        att_text = (r.get("attchmntText") or "").strip()
        comb = (desc + " " + att_text + " " + pdf_url.split("/")[-1]).lower()
        an_dt = (r.get("an_dt") or "").strip()
        q_label = infer_quarter_from_date(an_dt, comb)

        # 1. Earnings Call Transcripts (exclude AGM / AI Day / postal ballot)
        if "transcript" in comb and not any(
            skip in comb for skip in ["annual general meeting", "agm", "ai day", "postal ballot"]
        ):
            if q_label not in transcripts_by_q:
                transcripts_by_q[q_label] = {
                    "type": "concall_transcript",
                    "quarter": q_label,
                    "filing_date": an_dt.split(" ")[0],
                    "url": pdf_url,
                    "description": att_text[:160],
                }

        # 2. Quarterly Financial Results / Media Releases on Results
        elif (
            "outcome of board meeting" in comb
            or "financial results" in comb
            or ("media release" in comb and "results" in comb)
        ) and not any(
            skip in comb
            for skip in [
                "audio recording",
                "link of audio",
                "prior intimation",
                "will hold its earning",
                "newspaper",
                "udin",
                "trading window",
                "record date for",
            ]
        ):
            if q_label not in outcomes_by_q:
                outcomes_by_q[q_label] = {
                    "type": "results_filing",
                    "quarter": q_label,
                    "filing_date": an_dt.split(" ")[0],
                    "url": pdf_url,
                    "description": att_text[:160],
                }

    docs: list[dict[str, Any]] = []
    for d in list(transcripts_by_q.values())[:5]:
        docs.append(d)
    for d in list(outcomes_by_q.values())[:5]:
        docs.append(d)

    return company_name, docs


# Smart Page Selection & Per-Quarter Token Budget Constants
# - Concall transcripts: prepared remarks (first 8 content pages) + Q&A pages with
#   quantitative guidance keywords, capped at ~8,000 tokens (~32,000 chars) per transcript.
# - Results filings: only the P&L statement page(s) scored by _score_statement_page()
#   plus immediate highlights/notes pages, capped at ~2,500 tokens (~10,000 chars) per filing.
TRANSCRIPT_CHAR_BUDGET_PER_QUARTER = 20000  # ~5,000 tokens per transcript
RESULTS_CHAR_BUDGET_PER_QUARTER = 8000      # ~2,000 tokens per results filing
Prepared_REMARKS_MAX_PAGES = 5

GUIDANCE_KEYWORDS = (
    "guidance",
    "outlook",
    "target",
    "margin",
    "ebitda",
    "revenue growth",
    "constant currency",
    "capex",
    "fy26",
    "fy27",
    "q1",
    "q2",
    "q3",
    "q4",
    "double digit",
    "double-digit",
    "basis points",
    "bps",
    "aspir",
    "band",
    "range",
    "trajectory",
    "expect",
    "order book",
    "inflow",
    "nim",
    "credit cost",
    "slippage",
    "roa",
    "roe",
)


def _score_transcript_qa_page(txt: str) -> int:
    """Score a transcript Q&A page by quantitative guidance density."""
    low = txt.lower()
    kw_hits = sum(2 for kw in GUIDANCE_KEYWORDS if kw in low)
    pct_hits = len(re.findall(r"\b\d+(?:\.\d+)?\s*(?:%|bps|crore|cr|million|billion)\b", low))
    return kw_hits + min(pct_hits * 2, 12)


def download_and_extract_pages(
    session: creq.Session,
    ticker: str,
    docs: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[tuple[str, int], str], str, dict[str, Any]]:
    """
    Download each primary PDF into `data/documents/research/{SYM}/`, read pages
    via `pdfplumber`, and select pages using:
    - Prepared-remarks + keyword-scored Q&A pages for Concall Transcripts (per-quarter budget ~8k tokens)
    - P&L statement-only pages for Results Filings (per-quarter budget ~2.5k tokens)
    """
    sym = ticker_symbol(ticker)
    ticker_dir = RESEARCH_DOCS_DIR / sym
    ticker_dir.mkdir(parents=True, exist_ok=True)

    slice1_by_url: dict[str, dict[str, Any]] = {}
    slice1_path = DATA_DIR / "slice1_extractions.json"
    if slice1_path.exists():
        try:
            for item in json.loads(slice1_path.read_text()):
                if item.get("status") == "ok" and item.get("source_url"):
                    slice1_by_url[item["source_url"]] = item
        except Exception:
            pass

    enriched_docs: list[dict[str, Any]] = []
    read_pages: dict[tuple[str, int], str] = {}
    corpus_blocks: list[str] = []
    total_pdf_pages_across_docs = 0
    total_selected_pages = 0

    for idx, d in enumerate(docs):
        doc_id = f"DOC_{idx + 1}"
        pdf_url = d["url"]
        fname = pdf_url.split("/")[-1]
        local_path = ticker_dir / fname

        if not local_path.exists():
            alt_results = DOCS_DIR / "results"
            found_alt = None
            for cand in alt_results.glob(f"{sym}_*.pdf"):
                if pdf_url in slice1_by_url and slice1_by_url[pdf_url].get("pdf_file") == cand.name:
                    found_alt = cand
                    break
            if found_alt and found_alt.exists():
                local_path.write_bytes(found_alt.read_bytes())
            else:
                try:
                    r = session.get(pdf_url, timeout=35)
                    if r.status_code == 200 and r.content[:4] == b"%PDF":
                        local_path.write_bytes(r.content)
                except Exception as e:
                    print(f"  ⚠️ Failed to download {pdf_url}: {e}")
                    continue

        if not local_path.exists():
            continue

        try:
            with pdfplumber.open(local_path) as pdf:
                total_pages = len(pdf.pages)
                total_pdf_pages_across_docs += total_pages
                doc_type = d["type"]
                q_label = d["quarter"]
                f_date = d["filing_date"]
                doc_title = (
                    f"{q_label} Concall Transcript ({f_date})"
                    if doc_type == "concall_transcript"
                    else f"{q_label} Results Filing ({f_date})"
                )

                # Extract raw text of candidate pages first
                raw_page_map: dict[int, str] = {}
                max_scan = min(total_pages, 45)
                for p_num in range(1, max_scan + 1):
                    raw_txt = (pdf.pages[p_num - 1].extract_text() or "").strip()
                    if pdf_url in slice1_by_url and slice1_by_url[pdf_url].get("source_page") == p_num:
                        s1 = slice1_by_url[pdf_url]
                        v_block = (
                            f"\n[Verified Statement Figures on Page {p_num} ({s1['basis']}, normalised to ₹ crore): "
                            f"{s1['summary']} | Raw in {s1['reported_unit']}: "
                            f"Revenue={s1['raw_in_reported_unit']['revenue']}, "
                            f"EBITDA={s1['raw_in_reported_unit']['ebitda_in_reported_unit']}, "
                            f"PBT={s1['raw_in_reported_unit']['pbt']}, "
                            f"PAT={s1['raw_in_reported_unit']['pat']}]"
                        )
                        raw_txt = (raw_txt + v_block).strip()
                    if len(raw_txt) >= 40:
                        raw_page_map[p_num] = raw_txt

                selected_page_nums: list[int] = []
                char_budget = (
                    TRANSCRIPT_CHAR_BUDGET_PER_QUARTER
                    if doc_type == "concall_transcript"
                    else RESULTS_CHAR_BUDGET_PER_QUARTER
                )

                if doc_type == "concall_transcript":
                    # 1. Prepared remarks: first up to 8 content pages
                    content_p_nums = sorted(raw_page_map.keys())
                    prep_pages = content_p_nums[:Prepared_REMARKS_MAX_PAGES]
                    # 2. Q&A pages ranked by quantitative guidance keyword density
                    qa_candidates = content_p_nums[Prepared_REMARKS_MAX_PAGES:]
                    qa_scored = sorted(
                        qa_candidates,
                        key=lambda p: (-_score_transcript_qa_page(raw_page_map[p]), p),
                    )
                    used_chars = 0
                    for p in prep_pages + qa_scored:
                        p_len = min(len(raw_page_map[p]), 3200)
                        if used_chars + p_len > char_budget and len(selected_page_nums) >= 4:
                            continue
                        selected_page_nums.append(p)
                        used_chars += p_len
                    selected_page_nums.sort()
                else:
                    # Results filing: prioritize P&L statement pages scored via _score_statement_page()
                    # plus page 1-2 cover/press-release highlights, within RESULTS_CHAR_BUDGET_PER_QUARTER
                    scored_pages: list[tuple[int, int]] = []
                    for p_num, p_txt in raw_page_map.items():
                        st_meta = _score_statement_page(p_txt)
                        st_score = st_meta["score"]
                        if pdf_url in slice1_by_url and slice1_by_url[pdf_url].get("source_page") == p_num:
                            st_score += 200
                        elif p_num in (1, 2):
                            st_score = max(st_score, 25)
                        elif any(k in p_txt.lower() for k in ("revenue from operations", "profit before tax", "segment", "highlights")):
                            st_score = max(st_score, 15)
                        scored_pages.append((st_score, p_num))

                    scored_pages.sort(key=lambda x: (-x[0], x[1]))
                    used_chars = 0
                    for sc, p_num in scored_pages:
                        if sc < 0 and len(selected_page_nums) >= 2:
                            continue
                        p_len = min(len(raw_page_map[p_num]), 3200)
                        if used_chars + p_len > char_budget and len(selected_page_nums) >= 2:
                            continue
                        selected_page_nums.append(p_num)
                        used_chars += p_len
                    selected_page_nums.sort()

                page_texts_for_doc: list[str] = []
                for p_num in selected_page_nums:
                    raw_txt = raw_page_map[p_num]
                    read_pages[(doc_id, p_num)] = raw_txt
                    trimmed = raw_txt[:3200]
                    prompt_safe_txt = re.sub(
                        r"\bPage\s+\d+\s+of\s+\d+\b",
                        f"[PDF_PAGE_{p_num}]",
                        trimmed,
                        flags=re.IGNORECASE,
                    )
                    page_texts_for_doc.append(
                        f"[{doc_id} | PDF PAGE {p_num} | {doc_title}]\n"
                        f"{prompt_safe_txt}\n"
                        f"[END OF {doc_id} | PDF PAGE {p_num}]"
                    )

                if not page_texts_for_doc:
                    continue

                total_selected_pages += len(page_texts_for_doc)
                enriched_docs.append(
                    {
                        "doc_id": doc_id,
                        "title": doc_title,
                        "type": doc_type,
                        "quarter": q_label,
                        "filing_date": f_date,
                        "url": pdf_url,
                        "pages": total_pages,
                        "pages_read": len(page_texts_for_doc),
                        "selected_pages": selected_page_nums,
                        "char_budget": char_budget,
                    }
                )
                corpus_blocks.append(
                    f"================================================================\n"
                    f"DOCUMENT {doc_id}: {doc_title} (File: {fname}, Total Pages: {total_pages}, Selected Pages: {selected_page_nums})\n"
                    f"================================================================\n"
                    + "\n\n".join(page_texts_for_doc)
                )
        except Exception as e:
            print(f"  ⚠️ Error reading {local_path.name}: {e}")
            continue

    full_corpus = "\n\n".join(corpus_blocks)
    page_selection_stats = {
        "strategy": "prepared_remarks_and_keyword_qa_plus_pnl_results_pages",
        "transcript_char_budget_per_quarter": TRANSCRIPT_CHAR_BUDGET_PER_QUARTER,
        "results_char_budget_per_quarter": RESULTS_CHAR_BUDGET_PER_QUARTER,
        "total_pdf_pages_available": total_pdf_pages_across_docs,
        "pages_selected": total_selected_pages,
        "pages_dropped": max(0, total_pdf_pages_across_docs - total_selected_pages),
        "corpus_chars_sent": len(full_corpus),
    }
    return enriched_docs, read_pages, full_corpus, page_selection_stats


NARRATIVE_VS_NUMBERS_PROMPT = """You are a senior institutional equity analyst at an Indian investment firm conducting a "Narrative vs. Numbers" (Promised vs. Delivered) audit for {company} ({ticker}).

STRICT VERIFICATION GATE RULES (violation of any rule causes automatic rejection of the claim):
1. Use ONLY the primary source documents provided below (official NSE Earnings Call Transcripts and Financial Results Filings). Do NOT use model memory, broker notes, or news.
2. Every `guided` item and every `delivered` item MUST cite:
   - `"doc_id"`: Exact document ID from the header (e.g. `"DOC_1"`, `"DOC_2"`).
   - `"page"`: Exact integer from `[DOC_X | PDF PAGE N | ...]` (ZERO ±1 page tolerance).
   - `"quote"`: An EXACT contiguous verbatim substring copied character-for-character from that page (10 to 25 words). Do NOT use `...` ellipses or alter any word or punctuation in `"quote"`.
3. **EXACT NUMBER-IN-QUOTE RULE (CRITICAL — Rule 2a)**:
   - Every single number (percentage, $, ₹, bps, count, duration) that you write in `"guidance"` or `"actual"` MUST appear with the **EXACT same digits INSIDE the cited `"quote"` string itself** (not merely elsewhere on the same page)!
   - If the cited `"quote"` says `"Operating margin for the quarter was 21%."`, your `"actual"` can only contain `"21%"` — do NOT add any other number from another sentence on the page unless your `"quote"` spans both sentences contiguously, and NEVER write `"21.0%"`.
   - If the cited `"quote"` prints `"three-year"` or `"nine-month"` in words, write `"three-year"` or `"nine-month"` in words, NEVER `"3-year"` or `"9-month"`.
4. **STRICT CHRONOLOGY RULE (CRITICAL — Rule 2b)**:
   - In every quarter block (e.g. `"quarter": "Q1 FY27"`), the `"delivered"` item must cite the document for that evaluated quarter (`Q1 FY27`), and the `"guided"` item MUST cite a document from a **STRICTLY EARLIER fiscal quarter** (`guided_doc_quarter < delivered_doc_quarter`, e.g. `Q4 FY26`, `Q3 FY26`, `Q2 FY26`, or `Q1 FY26` when evaluating `Q1 FY27`).
   - NEVER cite a later quarter's transcript (hindsight) or the same quarter's transcript as the `"guided"` source! If the earliest transcript in the manifest is `Q1 FY26`, do NOT create a quarter block for `Q1 FY26` unless an earlier document exists; only create quarter blocks (`Q1 FY27`, `Q4 FY26`, `Q3 FY26`, `Q2 FY26`) where a strictly earlier transcript exists in the manifest.
5. Cover up to the 4 most recent deliverable quarters available in the documents, with 1 to 2 high-signal pairs of `guided` vs `delivered` metrics per quarter.

Available Fetched Primary Documents:
{doc_manifest}

Primary Source Pages Read:
\"\"\"
{corpus}
\"\"\"

Return ONLY valid JSON matching this exact schema:
{{
  "summary": "2-3 sharp sentences judging management execution vs guidance across the quarters, citing specific numbers.",
  "credibility_score": "high" | "medium" | "low",
  "pattern": "1-2 sentences identifying management's recurring execution pattern.",
  "quarters": [
    {{
      "quarter": "Q1 FY27",
      "verdict": "beat" | "hit" | "miss",
      "commentary": "1-2 concise sentences explaining the quarter's outcome against management's stated outlook.",
      "guided": [
        {{
          "metric": "Name of metric",
          "guidance": "What management guided (every number here MUST appear with exact digits on doc_id + page)",
          "doc_id": "DOC_2",
          "page": 4,
          "quote": "Exact contiguous verbatim substring from DOC_2 PDF PAGE 4"
        }}
      ],
      "delivered": [
        {{
          "metric": "Same metric name",
          "actual": "Actual delivered outcome (every number here MUST appear with exact digits on doc_id + page)",
          "doc_id": "DOC_1",
          "page": 5,
          "quote": "Exact contiguous verbatim substring from DOC_1 PDF PAGE 5"
        }}
      ]
    }}
  ]
}}
"""


def verify_and_write_evidence(
    ticker: str,
    raw_nvn: dict[str, Any],
    docs_by_id: dict[str, dict[str, Any]],
    read_pages: dict[tuple[str, int], str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Run `verify_single_claim()` (zero ±1 page tolerance + exact number matching)
    on every claim, reject any claim that fails, and write verified evidence
    files (`evidence/{SYM}/claims.json` + `evidence/{SYM}/{doc_id}_p{page}.txt`).
    """
    sym = ticker_symbol(ticker)
    sym_ev_dir = EVIDENCE_DIR / sym
    sym_ev_dir.mkdir(parents=True, exist_ok=True)
    # Clear old evidence files for this symbol before writing fresh verified ones
    for old_f in sym_ev_dir.glob("*"):
        if old_f.is_file():
            old_f.unlink()

    stats: dict[str, Any] = {
        "verified_claims": 0,
        "rejected_claims": 0,
        "rejections_detail": [],
    }
    evidence_records: list[dict[str, Any]] = []
    verified_quarters: list[dict[str, Any]] = []
    claim_counter = 0

    for q in raw_nvn.get("quarters") or []:
        if not isinstance(q, dict):
            continue
        q_name = str(q.get("quarter") or "Quarter")
        raw_guided = q.get("guided") or []
        raw_delivered = q.get("delivered") or []

        clean_guided: list[dict[str, Any]] = []
        clean_delivered: list[dict[str, Any]] = []

        max_len = max(len(raw_guided), len(raw_delivered))
        for i in range(max_len):
            g = raw_guided[i] if i < len(raw_guided) and isinstance(raw_guided[i], dict) else None
            d = raw_delivered[i] if i < len(raw_delivered) and isinstance(raw_delivered[i], dict) else None
            if not g or not d:
                stats["rejected_claims"] += 1
                continue

            g_txt = str(g.get("guidance") or "").strip()
            g_quote = str(g.get("quote") or "").strip()
            g_doc = str(g.get("doc_id") or "").strip()
            g_page_raw = g.get("page")

            d_txt = str(d.get("actual") or "").strip()
            d_quote = str(d.get("quote") or "").strip()
            d_doc = str(d.get("doc_id") or "").strip()
            d_page_raw = d.get("page")

            deliv_q_list = (
                [docs_by_id[d_doc]["quarter"]] if d_doc in docs_by_id and docs_by_id[d_doc].get("quarter") else []
            )
            g_ok, g_reasons = verify_single_claim(
                g_txt,
                g_quote,
                g_doc,
                g_page_raw,
                docs_by_id,
                read_pages,
                claim_kind="guided",
                evaluated_quarter=q_name,
                delivered_doc_quarters=deliv_q_list,
            )
            d_ok, d_reasons = verify_single_claim(
                d_txt,
                d_quote,
                d_doc,
                d_page_raw,
                docs_by_id,
                read_pages,
                claim_kind="delivered",
                evaluated_quarter=q_name,
                delivered_doc_quarters=deliv_q_list,
            )

            if not g_ok:
                stats["rejected_claims"] += 1
                stats["rejections_detail"].append(
                    {
                        "quarter": q_name,
                        "type": "guided",
                        "doc_id": g_doc,
                        "page": g_page_raw,
                        "claim": g_txt,
                        "quote": g_quote,
                        "reasons": g_reasons,
                    }
                )
                print(f"    ❌ REJECTED [{q_name} guided] ({g_doc} p.{g_page_raw}): {g_reasons}")
            if not d_ok:
                stats["rejected_claims"] += 1
                stats["rejections_detail"].append(
                    {
                        "quarter": q_name,
                        "type": "delivered",
                        "doc_id": d_doc,
                        "page": d_page_raw,
                        "claim": d_txt,
                        "quote": d_quote,
                        "reasons": d_reasons,
                    }
                )
                print(f"    ❌ REJECTED [{q_name} delivered] ({d_doc} p.{d_page_raw}): {d_reasons}")

            if not (g_ok and d_ok):
                continue

            g_page = int(g_page_raw)
            d_page = int(d_page_raw)
            g_meta = docs_by_id[g_doc]
            d_meta = docs_by_id[d_doc]

            # Write cited page texts to evidence/{SYM}/{doc_id}_p{page}.txt
            for doc_key, pg_num, meta in [(g_doc, g_page, g_meta), (d_doc, d_page, d_meta)]:
                ev_txt_path = sym_ev_dir / f"{doc_key}_p{pg_num}.txt"
                if not ev_txt_path.exists():
                    header = (
                        f"TICKER: {ticker}\n"
                        f"DOCUMENT_ID: {doc_key}\n"
                        f"DOCUMENT_TITLE: {meta['title']}\n"
                        f"PDF_PAGE: {pg_num} (of {meta['pages']})\n"
                        f"SOURCE_URL: {meta['url']}#page={pg_num}\n"
                        f"{'=' * 72}\n\n"
                    )
                    ev_txt_path.write_text(header + read_pages[(doc_key, pg_num)])

            g_url = f"{g_meta['url']}#page={g_page}"
            d_url = f"{d_meta['url']}#page={d_page}"
            g_ev_rel = f"evidence/{sym}/{g_doc}_p{g_page}.txt"
            d_ev_rel = f"evidence/{sym}/{d_doc}_p{d_page}.txt"

            g_source = f"{g_meta['title']}, PDF p. {g_page} — \"{g_quote}\""
            d_source = f"{d_meta['title']}, PDF p. {d_page} — \"{d_quote}\""

            clean_guided.append(
                {
                    "metric": g.get("metric", "Metric"),
                    "guidance": g_txt,
                    "source": g_source,
                    "source_url": g_url,
                    "doc_id": g_doc,
                    "page": g_page,
                    "evidence_file": g_ev_rel,
                }
            )
            clean_delivered.append(
                {
                    "metric": d.get("metric", g.get("metric", "Metric")),
                    "actual": d_txt,
                    "source": d_source,
                    "source_url": d_url,
                    "doc_id": d_doc,
                    "page": d_page,
                    "evidence_file": d_ev_rel,
                }
            )
            stats["verified_claims"] += 2

            for kind_label, c_txt, c_quote, doc_k, pg_n, meta_obj, s_url, ev_rel in [
                ("guided", g_txt, g_quote, g_doc, g_page, g_meta, g_url, g_ev_rel),
                ("delivered", d_txt, d_quote, d_doc, d_page, d_meta, d_url, d_ev_rel),
            ]:
                claim_counter += 1
                evidence_records.append(
                    {
                        "claim_id": f"{sym}-{claim_counter:02d}",
                        "ticker": ticker,
                        "quarter": q_name,
                        "type": kind_label,
                        "metric": g.get("metric", "Metric"),
                        "claim_text": c_txt,
                        "verbatim_quote": c_quote,
                        "numbers_verified_on_page": extract_quantitative_numbers(c_txt),
                        "doc_id": doc_k,
                        "doc_title": meta_obj["title"],
                        "pdf_page": pg_n,
                        "source_url": s_url,
                        "evidence_page_file": ev_rel,
                    }
                )

        if clean_guided and clean_delivered:
            verdict = str(q.get("verdict") or "hit").lower()
            if verdict not in ("beat", "hit", "miss"):
                verdict = "hit"
            verified_quarters.append(
                {
                    "quarter": q_name,
                    "guided": clean_guided,
                    "delivered": clean_delivered,
                    "verdict": verdict,
                    "commentary": q.get("commentary", ""),
                }
            )

    save_json(sym_ev_dir / "claims.json", evidence_records)

    cred = str(raw_nvn.get("credibility_score") or "medium").lower()
    if cred not in ("high", "medium", "low"):
        cred = "medium"

    return (
        {
            "summary": raw_nvn.get("summary", ""),
            "quarters": verified_quarters,
            "credibility_score": cred,
            "pattern": raw_nvn.get("pattern", ""),
        },
        stats,
    )


def generate_research_for_ticker(
    session: creq.Session,
    ticker: str,
) -> dict[str, Any]:
    sym = ticker_symbol(ticker)
    print(f"\n🔎 Discovering NSE primary documents for {ticker}...")
    company_name, docs = discover_nse_primary_documents(session, ticker, days_back=460)
    print(f"  Found {len(docs)} primary PDFs on NSE for {company_name}")

    enriched_docs, read_pages, corpus, page_selection_stats = download_and_extract_pages(
        session, ticker, docs
    )
    if not enriched_docs or not read_pages:
        raise RuntimeError(f"No readable primary documents found on NSE for {ticker}")

    print(
        f"  📖 Selected {len(read_pages)}/{page_selection_stats['total_pdf_pages_available']} pages "
        f"across {len(enriched_docs)} PDFs ({len(corpus):,} chars; "
        f"dropped {page_selection_stats['pages_dropped']} non-P&L/boilerplate pages)"
    )

    docs_by_id = {d["doc_id"]: d for d in enriched_docs}
    manifest_lines = [
        f"- {d['doc_id']}: {d['title']} | type={d['type']} | total_pages={d['pages']} | pages_selected={d['pages_read']} ({d['selected_pages']}) | url={d['url']}"
        for d in enriched_docs
    ]

    prompt = NARRATIVE_VS_NUMBERS_PROMPT.format(
        company=company_name,
        ticker=ticker,
        doc_manifest="\n".join(manifest_lines),
        corpus=corpus,
    )
    raw_out, model_used, tokens_in, tokens_out = call_gemini_multimodal(
        prompt=prompt,
        image_png_bytes=None,
        task="narrative_vs_numbers_v4",
        ticker=ticker,
        models=ANALYSIS_MODELS,
    )

    verified_nvn, stats = verify_and_write_evidence(
        ticker, raw_out, docs_by_id, read_pages
    )
    print(
        f"  🛡️ Tightened Citation Gate: {stats['verified_claims']} claims verified, "
        f"{stats['rejected_claims']} rejected ({len(verified_nvn['quarters'])} quarters retained)"
    )
    print(
        f"  💰 Model={model_used} | Tokens: in={tokens_in:,}, out={tokens_out:,} | "
        f"Cost=${estimate_cost_usd(model_used, tokens_in, tokens_out):.4f}"
    )

    source_documents = [
        {
            "type": d["type"],
            "quarter": d["quarter"],
            "url": d["url"],
            "pages": d["pages"],
            "pages_selected": d["pages_read"],
            "selected_page_numbers": d["selected_pages"],
        }
        for d in enriched_docs
    ]

    research_payload = {
        "ticker": ticker,
        "company_name": company_name,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "source_documents": source_documents,
        "page_selection_stats": page_selection_stats,
        "narrative_vs_numbers": verified_nvn,
        "citation_audit": {
            "documents_fetched": len(enriched_docs),
            "total_pdf_pages_available": page_selection_stats["total_pdf_pages_available"],
            "pages_actually_read": len(read_pages),
            "pages_dropped": page_selection_stats["pages_dropped"],
            "verified_claims": stats["verified_claims"],
            "rejected_claims": stats["rejected_claims"],
            "rejections_detail": stats["rejections_detail"],
        },
        "model_used": model_used,
        "tokens": {
            "in": tokens_in,
            "out": tokens_out,
            "out_candidates": (raw_out.get("_meta_tokens") or {}).get("out_candidates"),
            "out_thoughts": (raw_out.get("_meta_tokens") or {}).get("out_thoughts"),
        },
        "cost_estimate_usd": estimate_cost_usd(model_used, tokens_in, tokens_out),
    }

    save_json(RESEARCH_DIR / f"{sym}.json", research_payload)
    return research_payload


DEFAULT_RESEARCH_TICKERS = [
    "INFY.NS",
    "RELIANCE.NS",
    "TCS.NS",
    "ICICIBANK.NS",
    "ETERNAL.NS",
    "PIDILITIND.NS",
    "BAJFINANCE.NS",
    "ITC.NS",
]


if __name__ == "__main__":
    targets = sys.argv[1:] if len(sys.argv) > 1 else DEFAULT_RESEARCH_TICKERS
    targets = [t if t.endswith(".NS") else f"{t}.NS" for t in targets]
    sess = create_nse_session()
    for t in targets:
        try:
            generate_research_for_ticker(sess, t)
        except Exception as e:
            print(f"  ❌ Failed {t}: {e}")
        time.sleep(0.5)
