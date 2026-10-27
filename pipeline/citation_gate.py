"""
FINN Pipeline — Hardened Citation Gate & Negative Test Suite.

Enforces strict primary-source verification on every "Narrative vs. Numbers"
claim (`guided` and `delivered`):
1. `valid_doc_id`: `doc_id` must exist in the fetched NSE PDF manifest.
2. `exact_page_read`: `(doc_id, page)` must exist in `read_pages` (NO ±1 page
   tolerance — the exact integer page number cited must have been extracted).
3. `contiguous_quote_on_page`: The cited `quote` (after normalising whitespace
   and ellipses `...`) must appear verbatim on `read_pages[(doc_id, page)]`.
4. `exact_numbers_on_page`: Every quantitative number (percentage, $, ₹, bps,
   count, multiple) in BOTH `claim_text` (`guidance` or `actual`) AND `quote`
   must appear as an exact number token on `read_pages[(doc_id, page)]`
   (including exact decimal digits: e.g. `21.0` is rejected if the page only
   prints `21`, and `3.2%` is rejected if the page prints `3.1%`).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


# Standard non-quantitative tokens in Indian financial filings (quarter/FY labels,
# network generation 5G, business model 1P/3P, segment O2C, field KG-D6).
LABEL_TOKEN_RE = re.compile(
    r"\b(?:Q[1-4]|FY\s*'?\d{2,4}|[12]H|H[12]|5G|4G|1P|3P|O2C|KG-D6|B2B|B2C)\b",
    re.IGNORECASE,
)

# Number pattern capturing integers and decimals (with optional thousand commas)
NUMBER_TOKEN_RE = re.compile(r"(?<![A-Za-z])(\d+(?:,\d+)*(?:\.\d+)?)(?![A-Za-z])")


def extract_quantitative_numbers(text: str) -> list[str]:
    """
    Extract all quantitative number strings from `text` after masking out
    quarter/fiscal-year labels (Q1..Q4, FY26, 1H, 5G, 1P, O2C, KG-D6).
    Normalises thousand-separator commas ('72,275' -> '72275') while preserving
    exact decimal digits ('21.0' stays '21.0', NOT '21').
    """
    if not text:
        return []
    masked = LABEL_TOKEN_RE.sub(" ", text)
    raw_nums = NUMBER_TOKEN_RE.findall(masked)
    return [n.replace(",", "") for n in raw_nums]


def _normalise_for_substring(s: str) -> str:
    """Lowercase and collapse runs of whitespace/punctuation to single spaces."""
    return re.sub(r"[^a-z0-9%.]+", " ", s.lower()).strip()


def verify_single_claim(
    claim_text: str,
    quote: str,
    doc_id: str,
    page: Any,
    docs_by_id: dict[str, dict[str, Any]],
    read_pages: dict[tuple[str, int], str],
) -> tuple[bool, list[str]]:
    """
    Verify a single claim against `docs_by_id` and `read_pages` with ZERO page
    tolerance. Returns `(passed, rejection_reasons)`.
    """
    reasons: list[str] = []

    # 1. Check doc_id exists in fetched manifest
    doc_id_clean = str(doc_id or "").strip()
    if not doc_id_clean or doc_id_clean not in docs_by_id:
        reasons.append(f"invalid_doc_id ({doc_id_clean!r} not in fetched manifest)")
        return False, reasons

    # 2. Check exact page was read (NO ±1 page tolerance)
    try:
        page_int = int(page)
    except (TypeError, ValueError):
        reasons.append(f"non_integer_page ({page!r})")
        return False, reasons

    if (doc_id_clean, page_int) not in read_pages:
        reasons.append(
            f"page_not_read (({doc_id_clean}, p.{page_int}) not in read_pages; ±1 tolerance disabled)"
        )
        return False, reasons

    page_text = read_pages[(doc_id_clean, page_int)]
    norm_page = _normalise_for_substring(page_text)
    page_numbers = set(extract_quantitative_numbers(page_text))

    # 3. Verbatim quote check on the exact page
    quote_clean = (quote or "").strip()
    if len(quote_clean) < 8:
        reasons.append("quote_too_short_or_missing")
        return False, reasons

    # Split on '...' if the LLM elided middle words, and require every segment to
    # appear as a contiguous normalised substring on `page_text`.
    segments = [
        _normalise_for_substring(seg)
        for seg in re.split(r"\.{2,}|…", quote_clean)
        if len(_normalise_for_substring(seg)) >= 4
    ]
    if not segments:
        reasons.append("quote_empty_after_normalisation")
        return False, reasons

    for seg in segments:
        if seg not in norm_page:
            reasons.append(
                f"quote_not_on_page (segment {seg[:60]!r} not found on {doc_id_clean} p.{page_int})"
            )
            break

    # 4. Every quantitative number in `quote` must appear on the page
    quote_nums = extract_quantitative_numbers(quote_clean)
    missing_quote_nums = [n for n in quote_nums if n not in page_numbers]
    if missing_quote_nums:
        reasons.append(
            f"quote_numbers_missing_on_page ({missing_quote_nums} not on {doc_id_clean} p.{page_int})"
        )

    # 5. Every quantitative number in `claim_text` (guidance/actual) must appear on the page
    claim_nums = extract_quantitative_numbers(claim_text or "")
    missing_claim_nums = [n for n in claim_nums if n not in page_numbers]
    if missing_claim_nums:
        reasons.append(
            f"claim_numbers_missing_on_page ({missing_claim_nums} in claim {claim_text!r} not on {doc_id_clean} p.{page_int})"
        )

    return len(reasons) == 0, reasons


def run_negative_test_suite(
    docs_by_id: dict[str, dict[str, Any]],
    read_pages: dict[tuple[str, int], str],
) -> list[dict[str, Any]]:
    """
    Run 10 deliberately corrupted claims against real INFY.NS read_pages.
    All 10 MUST be rejected.
    """
    # Known real reference on INFY.NS:
    # DOC_4 = Q2 FY26 Concall Transcript (21-Oct-2025)
    #   PDF Page 3 (which has footer "Page 2 of 37") contains:
    #   - "revenues for the quarter grew 2.2% sequentially and 2.9% year-on-year in constant currency"
    #   - "The new guidance is growth between 2% and 3% in constant currency terms for the full year."
    #   - "Our operating margin was 21%."
    # DOC_3 = Q3 FY26 Concall Transcript (19-Jan-2026)
    #   PDF Page 4 contains:
    #   - "The new revenue growth guidance for this financial year is 3% to 3.5% growth in constant currency"
    test_cases = [
        {
            "id": 1,
            "corruption_type": "Wrong page number (PDF p. 15 instead of PDF p. 3)",
            "claim_text": "Q2 FY26 revenue grew 2.2% QoQ and 2.9% YoY in CC terms.",
            "quote": "revenues for the quarter grew 2.2% sequentially and 2.9% year-on-year in constant currency",
            "doc_id": "DOC_4",
            "page": 15,
        },
        {
            "id": 2,
            "corruption_type": "Off-by-one page number (PDF p. 2 footer page instead of PDF p. 3 — tests removal of ±1 page tolerance)",
            "claim_text": "Q2 FY26 revenue grew 2.2% QoQ and 2.9% YoY in CC terms.",
            "quote": "revenues for the quarter grew 2.2% sequentially and 2.9% year-on-year in constant currency",
            "doc_id": "DOC_4",
            "page": 2,
        },
        {
            "id": 3,
            "corruption_type": "Non-existent doc_id (DOC_99)",
            "claim_text": "Q2 FY26 revenue grew 2.2% QoQ and 2.9% YoY in CC terms.",
            "quote": "revenues for the quarter grew 2.2% sequentially and 2.9% year-on-year in constant currency",
            "doc_id": "DOC_99",
            "page": 3,
        },
        {
            "id": 4,
            "corruption_type": "Page outside read range (DOC_6 p. 190 of 195 — unread auditor/annexure page)",
            "claim_text": "Q2 FY26 revenue grew 2.2% QoQ and 2.9% YoY in CC terms.",
            "quote": "revenues for the quarter grew 2.2% sequentially and 2.9% year-on-year in constant currency",
            "doc_id": "DOC_6",
            "page": 190,
        },
        {
            "id": 5,
            "corruption_type": "Quote on valid page (PDF p. 3) with one number changed ('2.4% sequentially' instead of '2.2% sequentially')",
            "claim_text": "Q2 FY26 revenue grew 2.4% QoQ and 2.9% YoY in CC terms.",
            "quote": "revenues for the quarter grew 2.4% sequentially and 2.9% year-on-year in constant currency",
            "doc_id": "DOC_4",
            "page": 3,
        },
        {
            "id": 6,
            "corruption_type": "Valid verbatim quote on PDF p. 3, but claim text alters one number ('3.9% YoY' instead of '2.9% YoY')",
            "claim_text": "Q2 FY26 revenue grew 2.2% QoQ and 3.9% YoY in CC terms.",
            "quote": "revenues for the quarter grew 2.2% sequentially and 2.9% year-on-year in constant currency",
            "doc_id": "DOC_4",
            "page": 3,
        },
        {
            "id": 7,
            "corruption_type": "Valid verbatim quote on PDF p. 3 ('21%'), but claim text adds unprinted decimal ('21.0%')",
            "claim_text": "Delivered Q2 FY26 operating margin of 21.0%.",
            "quote": "Our operating margin was 21%.",
            "doc_id": "DOC_4",
            "page": 3,
        },
        {
            "id": 8,
            "corruption_type": "Quote from a different quarter's transcript (Q3 FY26 DOC_3 p. 4 cited against Q2 FY26 DOC_4 p. 3)",
            "claim_text": "Revised revenue growth guidance to 3% to 3.5% growth in constant currency.",
            "quote": "The new revenue growth guidance for this financial year is 3% to 3.5% growth in constant currency",
            "doc_id": "DOC_4",
            "page": 3,
        },
        {
            "id": 9,
            "corruption_type": "Valid verbatim quote on PDF p. 3, but claim invents a bps figure (50 bps expansion) not on the page",
            "claim_text": "Operating margin was 21%, expanding 50 bps QoQ.",
            "quote": "Our operating margin was 21%.",
            "doc_id": "DOC_4",
            "page": 3,
        },
        {
            "id": 10,
            "corruption_type": "Valid verbatim quote on PDF p. 3, but claim invents a dollar deal-value count ($4.5 billion) not on the page",
            "claim_text": "Growth between 2% and 3% backed by $4.5 billion in large deals.",
            "quote": "The new guidance is growth between 2% and 3% in constant currency terms for the full year.",
            "doc_id": "DOC_4",
            "page": 3,
        },
    ]

    results = []
    for tc in test_cases:
        passed, reasons = verify_single_claim(
            claim_text=tc["claim_text"],
            quote=tc["quote"],
            doc_id=tc["doc_id"],
            page=tc["page"],
            docs_by_id=docs_by_id,
            read_pages=read_pages,
        )
        results.append(
            {
                "id": tc["id"],
                "corruption_type": tc["corruption_type"],
                "doc_id": tc["doc_id"],
                "page": tc["page"],
                "claim_text": tc["claim_text"],
                "quote": tc["quote"],
                "rejected": not passed,
                "rejection_reasons": reasons,
            }
        )
    return results


if __name__ == "__main__":
    from config import DATA_DIR, RESEARCH_DIR, content_hash, get_cached, save_json
    from fetch_announcements import create_nse_session
    from generate_research import (
        NARRATIVE_VS_NUMBERS_PROMPT,
        discover_nse_primary_documents,
        download_and_extract_pages,
    )

    sess = create_nse_session()
    _, infy_docs = discover_nse_primary_documents(sess, "INFY.NS", days_back=460)
    infy_enriched, infy_pages, _ = download_and_extract_pages(sess, "INFY.NS", infy_docs)
    infy_by_id = {d["doc_id"]: d for d in infy_enriched}

    neg_results = run_negative_test_suite(infy_by_id, infy_pages)
    save_json(DATA_DIR / "negative_test_results.json", neg_results)
    print("=== ITEM 1: 10-CLAIM NEGATIVE TEST SUITE ===")
    caught = sum(1 for r in neg_results if r["rejected"])
    for r in neg_results:
        cid = r["id"]
        rej = r["rejected"]
        ctype = r["corruption_type"]
        print(f"Test #{cid:2d} | Rejected={rej} | {ctype}")
        for reason in r["rejection_reasons"]:
            print(f"         -> {reason}")
    print(f"Total negative tests caught: {caught}/10\n")

    print("=== ITEM 2: AUDIT OF PREVIOUS 60 CLAIMS UNDER TIGHTENED GATE ===")
    total_pass = 0
    total_rej = 0
    for sym in ["INFY.NS", "RELIANCE.NS", "TCS.NS", "ICICIBANK.NS", "ETERNAL.NS"]:
        _, docs = discover_nse_primary_documents(sess, sym, days_back=460)
        enriched, read_pages, corpus = download_and_extract_pages(sess, sym, docs)
        docs_by_id = {d["doc_id"]: d for d in enriched}
        manifest_lines = [
            f"- {d['doc_id']}: {d['title']} | type={d['type']} | total_pages={d['pages']} | pages_read={d['pages_read']} | url={d['url']}"
            for d in enriched
        ]
        comp_file = RESEARCH_DIR / f"{sym.split('.')[0]}.json"
        comp = json.loads(comp_file.read_text())["company_name"]
        prompt = NARRATIVE_VS_NUMBERS_PROMPT.format(
            company=comp,
            ticker=sym,
            doc_manifest="\n".join(manifest_lines),
            corpus=corpus[:180000],
        )
        raw_out = get_cached(content_hash(prompt), "narrative_vs_numbers_v1") or {}
        p_cnt = 0
        r_cnt = 0
        for q in raw_out.get("quarters", []):
            q_name = q.get("quarter")
            for kind, key_txt in [("guided", "guidance"), ("delivered", "actual")]:
                for item in q.get(kind, []):
                    ok, reasons = verify_single_claim(
                        claim_text=item.get(key_txt, ""),
                        quote=item.get("quote", ""),
                        doc_id=item.get("doc_id", ""),
                        page=item.get("page"),
                        docs_by_id=docs_by_id,
                        read_pages=read_pages,
                    )
                    if ok:
                        p_cnt += 1
                    else:
                        r_cnt += 1
                        doc_ref = item.get("doc_id")
                        pg_ref = item.get("page")
                        print(f"  ❌ [{sym} | {q_name} | {kind}] ({doc_ref} p.{pg_ref}) REJECTED:")
                        for rn in reasons:
                            print(f"       - {rn}")
        total_pass += p_cnt
        total_rej += r_cnt
        print(f"  ==> {sym}: {p_cnt} passed, {r_cnt} rejected (out of {p_cnt + r_cnt})\n")
    print(f"OVERALL ACROSS 5 COMPANIES: {total_pass} passed, {total_rej} rejected (out of {total_pass + total_rej})")

