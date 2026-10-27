"""
FINN Pipeline — Slice 5: On-Demand Company Research ("Narrative vs. Numbers").

Grounded STRICTLY in primary sources fetched from NSE (`nsearchives.nseindia.com`):
- Earnings conference call transcripts (`concall_transcript`)
- Quarterly financial results & board outcome filings (`results_filing`)

Strict Citation Gate (enforced in Python before saving):
1. Every `guided` and `delivered` claim must return `doc_id`, integer `page`,
   and a short `verbatim_quote` from that page.
2. Python checks that `doc_id` is a real downloaded PDF and `(doc_id, page)` is
   in `read_pages` (meaning that exact page was extracted and non-empty).
3. Any claim without a valid `(doc_id, page)` in `read_pages` is REJECTED.
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

from config import (
    DATA_DIR,
    DOCS_DIR,
    RESEARCH_DIR,
    estimate_cost_usd,
    save_json,
    ticker_symbol,
)
from extract_results import call_gemini_multimodal
from fetch_announcements import create_nse_session


RESEARCH_DOCS_DIR = DOCS_DIR / "research"
RESEARCH_DOCS_DIR.mkdir(parents=True, exist_ok=True)

ANALYSIS_MODELS = [
    "gemini-3.6-flash",
    "gemini-3-flash-preview",
    "gemini-3.5-flash-lite",
]


def infer_quarter_from_date(an_dt_str: str, text: str = "") -> str:
    """
    Infer Indian fiscal quarter label (e.g. 'Q2 FY27') from an NSE filing date
    or filing description.
    Indian FY runs April 1 to March 31:
    - Filing in Apr/May (for period ended Mar 31, YYYY) -> Q4 FY{YY}
    - Filing in Jul/Aug (for period ended Jun 30, YYYY) -> Q1 FY{YY+1}
    - Filing in Oct/Nov (for period ended Sep 30, YYYY) -> Q2 FY{YY+1}
    - Filing in Jan/Feb (for period ended Dec 31, YYYY-1) -> Q3 FY{YY}
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
    else:  # Jan, Feb, Mar
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
        desc = (r.get("desc") or "").strip()
        att_text = (r.get("attchmntText") or "").strip()
        comb = (desc + " " + att_text + " " + pdf_url.split("/")[-1]).lower()
        an_dt = (r.get("an_dt") or "").strip()
        q_label = infer_quarter_from_date(an_dt, comb)

        # 1. Earnings Call Transcripts (exclude AGM / AI Day / non-earnings transcripts)
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
            # Prefer full financial results / media release packet
            if q_label not in outcomes_by_q:
                outcomes_by_q[q_label] = {
                    "type": "results_filing",
                    "quarter": q_label,
                    "filing_date": an_dt.split(" ")[0],
                    "url": pdf_url,
                    "description": att_text[:160],
                }

    # Combine up to 5 most recent transcripts + 5 most recent results outcomes
    docs: list[dict[str, Any]] = []
    for d in list(transcripts_by_q.values())[:5]:
        docs.append(d)
    for d in list(outcomes_by_q.values())[:5]:
        docs.append(d)

    return company_name, docs


def download_and_extract_pages(
    session: creq.Session,
    ticker: str,
    docs: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[tuple[str, int], str], str]:
    """
    Download each primary PDF into `data/documents/research/{SYM}/`, read pages
    via `pdfplumber`, and build:
    - `enriched_docs`: metadata list with `doc_id`, `pages`, `local_path`, `url`
    - `read_pages`: `{(doc_id, page_number): extracted_text}` for strict citation verification
    - `prompt_corpus`: formatted text corpus tagged with `[DOC_ID | Page N]`
    """
    sym = ticker_symbol(ticker)
    ticker_dir = RESEARCH_DOCS_DIR / sym
    ticker_dir.mkdir(parents=True, exist_ok=True)

    # Also load verified Slice 1 results extractions so if a scanned results PDF
    # has broken OCR on its statement page (like RELIANCE_Q1FY27.pdf p. 9 or
    # INFY_Q2FY27.pdf p. 18), that page's verified table summary is appended.
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

    for idx, d in enumerate(docs):
        doc_id = f"DOC_{idx + 1}"
        pdf_url = d["url"]
        fname = pdf_url.split("/")[-1]
        local_path = ticker_dir / fname

        if not local_path.exists():
            # Also check if already downloaded in data/documents/results/
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
                doc_type = d["type"]
                q_label = d["quarter"]
                f_date = d["filing_date"]
                doc_title = (
                    f"{q_label} Concall Transcript ({f_date})"
                    if doc_type == "concall_transcript"
                    else f"{q_label} Results Filing ({f_date})"
                )

                # Select pages to read:
                # - For concall transcripts (usually 12-22 pages), read up to 22 pages.
                # - For results filings (can be 15-195 pages), read first 18 pages
                #   PLUS any page matching Consolidated/Standalone financial results or press release.
                pages_to_read: list[int] = []
                if doc_type == "concall_transcript":
                    pages_to_read = list(range(1, min(total_pages, 24) + 1))
                else:
                    pages_to_read = list(range(1, min(total_pages, 18) + 1))
                    if pdf_url in slice1_by_url:
                        sp = int(slice1_by_url[pdf_url]["source_page"])
                        if sp not in pages_to_read and 1 <= sp <= total_pages:
                            pages_to_read.append(sp)
                    # Also scan up to page 40 for press release / media release / consolidated results pages
                    for p_i in range(19, min(total_pages, 45) + 1):
                        if p_i not in pages_to_read:
                            pages_to_read.append(p_i)

                page_texts_for_doc: list[str] = []
                for p_num in sorted(pages_to_read):
                    raw_txt = (pdf.pages[p_num - 1].extract_text() or "").strip()
                    # Append verified Slice 1 vision-extracted numbers if this is the exact statement page
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

                    if len(raw_txt) < 40:
                        continue

                    # Cap per-page characters to keep prompt dense and focused
                    trimmed = raw_txt[:3200]
                    read_pages[(doc_id, p_num)] = raw_txt
                    page_texts_for_doc.append(
                        f"[{doc_id} | Page {p_num} | {doc_title}]\n{trimmed}"
                    )

                if not page_texts_for_doc:
                    continue

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
                    }
                )
                corpus_blocks.append(
                    f"================================================================\n"
                    f"DOCUMENT {doc_id}: {doc_title} (File: {fname}, Total Pages: {total_pages})\n"
                    f"================================================================\n"
                    + "\n\n".join(page_texts_for_doc)
                )
        except Exception as e:
            print(f"  ⚠️ Error reading {local_path.name}: {e}")
            continue

    return enriched_docs, read_pages, "\n\n".join(corpus_blocks)


NARRATIVE_VS_NUMBERS_PROMPT = """You are a senior institutional equity analyst at an Indian investment firm conducting a "Narrative vs. Numbers" (Promised vs. Delivered) audit for {company} ({ticker}).

CRITICAL GROUNDING & CITATION RULES:
1. Use ONLY the primary source documents provided below (official NSE Earnings Call Transcripts and Financial Results Filings). Do NOT use model memory, broker notes, or news.
2. Every single `guided` item (what management guided, targeted, or committed to on the call/release) and `delivered` item (what the company actually delivered in that or the subsequent quarter's filing/transcript) MUST cite:
   - `"doc_id"`: Exact document ID from the header (e.g. `"DOC_1"`, `"DOC_2"`).
   - `"page"`: Exact integer page number from `[DOC_X | Page N | ...]`.
   - `"quote"`: A short verbatim phrase or figure from that exact page proving the claim.
3. Any claim whose `(doc_id, page)` was not in the provided pages will be automatically rejected by our verification gate. Never guess a page number.
4. For each quarter (up to the 4 most recent quarters covered by the documents), pair each `guided` item with a corresponding `delivered` item at the same array index so they compare side-by-side:
   - If management gave explicit quantitative guidance (e.g. FY constant-currency revenue growth %, operating margin band %, store addition target, capex/order inflow target, NIM/credit-cost range), quote the exact guidance band and compare against the actual delivered figure.
   - If management gave qualitative directional guidance on a key operating metric (e.g. margin expansion, store rollout, segment growth, debt reduction, asset quality), quote their stated commitment and compare against the actual delivered numbers from the results filing / subsequent transcript.
5. Assign `"verdict"`: `"beat"`, `"hit"`, or `"miss"` for each quarter, and an overall `"credibility_score"`: `"high"`, `"medium"`, or `"low"`.

Available Fetched Primary Documents:
{doc_manifest}

Primary Source Pages Read:
\"\"\"
{corpus}
\"\"\"

Return ONLY valid JSON matching this exact schema:
{{
  "summary": "2-3 sharp sentences judging management execution vs guidance across the last 4 quarters, citing specific numbers.",
  "credibility_score": "high" | "medium" | "low",
  "pattern": "1-2 sentences identifying management's recurring pattern (e.g., conservative initial guidance followed by upward revisions, or aggressive store targets with margin trade-offs).",
  "quarters": [
    {{
      "quarter": "Q2 FY27",
      "verdict": "beat" | "hit" | "miss",
      "commentary": "1-2 concise sentences explaining the quarter's outcome against management's stated outlook.",
      "guided": [
        {{
          "metric": "Name of metric (e.g. FY27 Revenue Growth Guidance / Operating Margin / Store Additions)",
          "guidance": "What management guided or stated (with exact numbers/targets)",
          "doc_id": "DOC_1",
          "page": 4,
          "quote": "Short verbatim quote from that page"
        }}
      ],
      "delivered": [
        {{
          "metric": "Same metric name",
          "actual": "Actual delivered number/outcome from the results filing or transcript",
          "doc_id": "DOC_5",
          "page": 18,
          "quote": "Short verbatim figure/quote from that page"
        }}
      ]
    }}
  ]
}}
"""


def _quote_verified_on_page(
    quote: str,
    doc_id: str,
    page: int,
    read_pages: dict[tuple[str, int], str],
) -> tuple[bool, int]:
    """
    Verify that the substantive words/numbers of `quote` actually appear on
    `(doc_id, page)` (or `page ± 1` if a sentence spans a page break).
    Returns `(is_verified, matched_page)`.
    """
    if not quote or len(quote.strip()) < 5:
        return False, page
    tokens = [
        t.lower()
        for t in re.findall(r"[A-Za-z0-9%.]+", quote)
        if len(t) >= 2
    ]
    if not tokens:
        return False, page

    for candidate_page in (page, page - 1, page + 1):
        page_txt = read_pages.get((doc_id, candidate_page))
        if not page_txt:
            continue
        low_page = page_txt.lower()
        matched = sum(1 for t in tokens if t in low_page)
        if matched / len(tokens) >= 0.65:
            return True, candidate_page
    return False, page


def verify_and_format_citations(
    raw_nvn: dict[str, Any],
    docs_by_id: dict[str, dict[str, Any]],
    read_pages: dict[tuple[str, int], str],
) -> tuple[dict[str, Any], dict[str, int]]:
    """
    Enforce the strict citation gate:
    - Reject any `guided` or `delivered` claim if `doc_id` is not in `docs_by_id`,
      `(doc_id, int(page))` is not in `read_pages`, or the verbatim quote tokens
      do not appear on that page.
    - Format `source` deterministically as `<Doc Title>, p. <page> — "<quote>"`.
    """
    stats = {"verified_claims": 0, "rejected_claims": 0}
    verified_quarters: list[dict[str, Any]] = []

    for q in raw_nvn.get("quarters") or []:
        if not isinstance(q, dict):
            continue
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

            g_doc = str(g.get("doc_id") or "").strip()
            d_doc = str(d.get("doc_id") or "").strip()
            try:
                g_page = int(g.get("page"))
                d_page = int(d.get("page"))
            except (TypeError, ValueError):
                stats["rejected_claims"] += 2
                continue

            if (g_doc, g_page) not in read_pages or g_doc not in docs_by_id:
                print(f"    ❌ REJECTED guided claim: ({g_doc}, p.{g_page}) not in read_pages")
                stats["rejected_claims"] += 1
                continue

            if (d_doc, d_page) not in read_pages or d_doc not in docs_by_id:
                print(f"    ❌ REJECTED delivered claim: ({d_doc}, p.{d_page}) not in read_pages")
                stats["rejected_claims"] += 1
                continue

            g_quote = (g.get("quote") or "").strip().replace('"', "'")
            d_quote = (d.get("quote") or "").strip().replace('"', "'")

            g_ok, g_page = _quote_verified_on_page(g_quote, g_doc, g_page, read_pages)
            d_ok, d_page = _quote_verified_on_page(d_quote, d_doc, d_page, read_pages)
            if not g_ok or not d_ok:
                print(
                    f"    ❌ REJECTED claim pair: quote text mismatch on ({g_doc}, p.{g_page}) or ({d_doc}, p.{d_page})"
                )
                stats["rejected_claims"] += 2
                continue

            g_meta = docs_by_id[g_doc]
            d_meta = docs_by_id[d_doc]

            g_source = f"{g_meta['title']}, p. {g_page}" + (f' — "{g_quote[:90]}"' if g_quote else "")
            d_source = f"{d_meta['title']}, p. {d_page}" + (f' — "{d_quote[:90]}"' if d_quote else "")

            clean_guided.append(
                {
                    "metric": g.get("metric", "Metric"),
                    "guidance": g.get("guidance", ""),
                    "source": g_source,
                }
            )
            clean_delivered.append(
                {
                    "metric": d.get("metric", g.get("metric", "Metric")),
                    "actual": d.get("actual", ""),
                    "source": d_source,
                }
            )
            stats["verified_claims"] += 2

        if clean_guided and clean_delivered:
            verdict = str(q.get("verdict") or "hit").lower()
            if verdict not in ("beat", "hit", "miss"):
                verdict = "hit"
            verified_quarters.append(
                {
                    "quarter": q.get("quarter", "Quarter"),
                    "guided": clean_guided,
                    "delivered": clean_delivered,
                    "verdict": verdict,
                    "commentary": q.get("commentary", ""),
                }
            )

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

    enriched_docs, read_pages, corpus = download_and_extract_pages(session, ticker, docs)
    if not enriched_docs or not read_pages:
        raise RuntimeError(f"No readable primary documents found on NSE for {ticker}")

    print(
        f"  📖 Read {len(read_pages)} pages across {len(enriched_docs)} PDFs "
        f"({len(corpus):,} chars)"
    )

    docs_by_id = {d["doc_id"]: d for d in enriched_docs}
    manifest_lines = [
        f"- {d['doc_id']}: {d['title']} | type={d['type']} | total_pages={d['pages']} | pages_read={d['pages_read']} | url={d['url']}"
        for d in enriched_docs
    ]

    prompt = NARRATIVE_VS_NUMBERS_PROMPT.format(
        company=company_name,
        ticker=ticker,
        doc_manifest="\n".join(manifest_lines),
        corpus=corpus[:180000],
    )

    raw_out, model_used, tokens_in, tokens_out = call_gemini_multimodal(
        prompt=prompt,
        image_png_bytes=None,
        task="narrative_vs_numbers_v1",
        ticker=ticker,
        models=ANALYSIS_MODELS,
    )

    verified_nvn, stats = verify_and_format_citations(raw_out, docs_by_id, read_pages)
    print(
        f"  🛡️ Citation gate: {stats['verified_claims']} claims verified, "
        f"{stats['rejected_claims']} rejected ({len(verified_nvn['quarters'])} quarters retained)"
    )

    source_documents = [
        {
            "type": d["type"],
            "quarter": d["quarter"],
            "url": d["url"],
            "pages": d["pages"],
        }
        for d in enriched_docs
    ]

    research_payload = {
        "ticker": ticker,
        "company_name": company_name,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "source_documents": source_documents,
        "narrative_vs_numbers": verified_nvn,
        "citation_audit": {
            "documents_fetched": len(enriched_docs),
            "pages_actually_read": len(read_pages),
            "verified_claims": stats["verified_claims"],
            "rejected_claims": stats["rejected_claims"],
        },
        "model_used": model_used,
        "tokens": {"in": tokens_in, "out": tokens_out},
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
        time.sleep(1.0)
