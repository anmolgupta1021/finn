"""
FINN Pipeline — Hardened Citation Gate (v3) & 12-Case Negative Test Suite.

Enforces strict primary-source verification on every "Narrative vs. Numbers"
claim (`guided` and `delivered`):
1. `valid_doc_id`: `doc_id` must exist in the fetched NSE PDF manifest.
2. `exact_page_read`: `(doc_id, page)` must exist in `read_pages` (NO ±1 page
   tolerance — the exact integer page number cited must have been extracted).
3. `contiguous_quote_on_page`: The cited `quote` (after normalising whitespace)
   must appear verbatim on `read_pages[(doc_id, page)]`.
4. `exact_numbers_on_page`: Every quantitative number in BOTH `claim_text`
   AND `quote` must appear on `read_pages[(doc_id, page)]` with exact digits.
5. `claim_numbers_in_quote` (Rule 2a): Every quantitative number in `claim_text`
   must appear inside the cited `quote` itself, not merely elsewhere on the same page.
6. `chronology_rule` (Rule 2b): For any `guided` claim, the cited document's
   fiscal period `(fy, quarter)` must be STRICTLY EARLIER (`<`) than the
   `delivered` document's fiscal period (rejects hindsight / same-quarter or
   later-quarter citations as "prior guidance").
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

QUARTER_PARSE_RE = re.compile(r"Q([1-4])\s*FY\s*'?(\d{2,4})", re.IGNORECASE)


def parse_quarter_rank(text: str | None) -> tuple[int, int] | None:
    """
    Parse a fiscal period string like 'Q1 FY27' or 'Q3 FY2026' into `(fy_2digit, q_int)`,
    e.g. `(27, 1)` or `(26, 3)`, so periods can be compared chronologically with `<`.
    """
    if not text:
        return None
    m = QUARTER_PARSE_RE.search(text)
    if not m:
        return None
    q_int = int(m.group(1))
    fy_raw = int(m.group(2))
    fy_2d = fy_raw % 100
    return (fy_2d, q_int)


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
    claim_kind: str | None = None,
    evaluated_quarter: str | None = None,
    delivered_doc_quarters: list[str] | None = None,
) -> tuple[bool, list[str]]:
    """
    Verify a single claim against `docs_by_id` and `read_pages` with:
    - ZERO ±1 page tolerance
    - Exact verbatim quote on page
    - Every number in `claim_text` present inside `quote` itself (Rule 2a)
    - Strict chronology `guided_period < delivered_period` for `guided` claims (Rule 2b)
    Returns `(passed, rejection_reasons)`.
    """
    reasons: list[str] = []

    # 1. Check doc_id exists in fetched manifest
    doc_id_clean = str(doc_id or "").strip()
    if not doc_id_clean or doc_id_clean not in docs_by_id:
        reasons.append(f"invalid_doc_id ({doc_id_clean!r} not in fetched manifest)")
        return False, reasons

    doc_meta = docs_by_id[doc_id_clean]

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
    quote_nums_set = set(quote_nums)
    missing_quote_nums = [n for n in quote_nums if n not in page_numbers]
    if missing_quote_nums:
        reasons.append(
            f"quote_numbers_missing_on_page ({missing_quote_nums} not on {doc_id_clean} p.{page_int})"
        )

    # 5. Every quantitative number in `claim_text` must appear on the page AND inside `quote` itself (Rule 2a)
    claim_nums = extract_quantitative_numbers(claim_text or "")
    missing_claim_nums_page = [n for n in claim_nums if n not in page_numbers]
    if missing_claim_nums_page:
        reasons.append(
            f"claim_numbers_missing_on_page ({missing_claim_nums_page} in claim {claim_text!r} not on {doc_id_clean} p.{page_int})"
        )

    missing_claim_nums_quote = [n for n in claim_nums if n not in quote_nums_set]
    if missing_claim_nums_quote:
        reasons.append(
            f"claim_numbers_missing_in_quote ({missing_claim_nums_quote} in claim {claim_text!r} not inside cited quote)"
        )

    # 6. Chronology Rule (Rule 2b): For `guided` claims, the guided doc's period must be
    # STRICTLY EARLIER than the delivered doc's period / evaluated quarter.
    if claim_kind == "guided":
        guided_q_str = doc_meta.get("quarter") or doc_meta.get("title") or ""
        g_rank = parse_quarter_rank(guided_q_str)

        target_ranks: list[tuple[int, int]] = []
        if evaluated_quarter:
            er = parse_quarter_rank(evaluated_quarter)
            if er:
                target_ranks.append(er)
        if delivered_doc_quarters:
            for dq in delivered_doc_quarters:
                dr = parse_quarter_rank(dq)
                if dr:
                    target_ranks.append(dr)

        if g_rank is not None and target_ranks:
            min_target = min(target_ranks)
            if not (g_rank < min_target):
                reasons.append(
                    f"chronology_violation (guided doc {doc_id_clean} [{guided_q_str}] period Q{g_rank[1]} FY{g_rank[0]} "
                    f"is not strictly earlier than delivered period Q{min_target[1]} FY{min_target[0]})"
                )

    return len(reasons) == 0, reasons


def run_negative_test_suite(
    docs_by_id: dict[str, dict[str, Any]],
    read_pages: dict[tuple[str, int], str],
) -> list[dict[str, Any]]:
    """
    Run 12 deliberately corrupted claims against real INFY.NS read_pages.
    All 12 MUST be rejected.
    """
    test_cases = [
        {
            "id": 1,
            "corruption_type": "Wrong page number (PDF p. 15 instead of PDF p. 3)",
            "claim_text": "Q2 FY26 revenue grew 2.2% QoQ and 2.9% YoY in CC terms.",
            "quote": "revenues for the quarter grew 2.2% sequentially and 2.9% year-on-year in constant currency",
            "doc_id": "DOC_4",
            "page": 15,
            "claim_kind": "delivered",
            "evaluated_quarter": "Q2 FY26",
        },
        {
            "id": 2,
            "corruption_type": "Off-by-one page number (PDF p. 2 footer page instead of PDF p. 3 — tests removal of ±1 page tolerance)",
            "claim_text": "Q2 FY26 revenue grew 2.2% QoQ and 2.9% YoY in CC terms.",
            "quote": "revenues for the quarter grew 2.2% sequentially and 2.9% year-on-year in constant currency",
            "doc_id": "DOC_4",
            "page": 2,
            "claim_kind": "delivered",
            "evaluated_quarter": "Q2 FY26",
        },
        {
            "id": 3,
            "corruption_type": "Non-existent doc_id (DOC_99)",
            "claim_text": "Q2 FY26 revenue grew 2.2% QoQ and 2.9% YoY in CC terms.",
            "quote": "revenues for the quarter grew 2.2% sequentially and 2.9% year-on-year in constant currency",
            "doc_id": "DOC_99",
            "page": 3,
            "claim_kind": "delivered",
            "evaluated_quarter": "Q2 FY26",
        },
        {
            "id": 4,
            "corruption_type": "Page outside read range (DOC_6 p. 190 of 195 — unread auditor/annexure page)",
            "claim_text": "Q2 FY26 revenue grew 2.2% QoQ and 2.9% YoY in CC terms.",
            "quote": "revenues for the quarter grew 2.2% sequentially and 2.9% year-on-year in constant currency",
            "doc_id": "DOC_6",
            "page": 190,
            "claim_kind": "delivered",
            "evaluated_quarter": "Q2 FY26",
        },
        {
            "id": 5,
            "corruption_type": "Quote on valid page (PDF p. 3) with one number changed ('2.4% sequentially' instead of '2.2% sequentially')",
            "claim_text": "Q2 FY26 revenue grew 2.4% QoQ and 2.9% YoY in CC terms.",
            "quote": "revenues for the quarter grew 2.4% sequentially and 2.9% year-on-year in constant currency",
            "doc_id": "DOC_4",
            "page": 3,
            "claim_kind": "delivered",
            "evaluated_quarter": "Q2 FY26",
        },
        {
            "id": 6,
            "corruption_type": "Valid verbatim quote on PDF p. 3, but claim text alters one number ('3.9% YoY' instead of '2.9% YoY')",
            "claim_text": "Q2 FY26 revenue grew 2.2% QoQ and 3.9% YoY in CC terms.",
            "quote": "revenues for the quarter grew 2.2% sequentially and 2.9% year-on-year in constant currency",
            "doc_id": "DOC_4",
            "page": 3,
            "claim_kind": "delivered",
            "evaluated_quarter": "Q2 FY26",
        },
        {
            "id": 7,
            "corruption_type": "Valid verbatim quote on PDF p. 3 ('21%'), but claim text adds unprinted decimal ('21.0%')",
            "claim_text": "Delivered Q2 FY26 operating margin of 21.0%.",
            "quote": "Our operating margin was 21%.",
            "doc_id": "DOC_4",
            "page": 3,
            "claim_kind": "delivered",
            "evaluated_quarter": "Q2 FY26",
        },
        {
            "id": 8,
            "corruption_type": "Quote from a different quarter's transcript (Q3 FY26 DOC_3 p. 4 cited against Q2 FY26 DOC_4 p. 3)",
            "claim_text": "Revised revenue growth guidance to 3% to 3.5% growth in constant currency.",
            "quote": "The new revenue growth guidance for this financial year is 3% to 3.5% growth in constant currency",
            "doc_id": "DOC_4",
            "page": 3,
            "claim_kind": "delivered",
            "evaluated_quarter": "Q2 FY26",
        },
        {
            "id": 9,
            "corruption_type": "Valid verbatim quote on PDF p. 3, but claim invents a bps figure (50 bps expansion) not on the page",
            "claim_text": "Operating margin was 21%, expanding 50 bps QoQ.",
            "quote": "Our operating margin was 21%.",
            "doc_id": "DOC_4",
            "page": 3,
            "claim_kind": "delivered",
            "evaluated_quarter": "Q2 FY26",
        },
        {
            "id": 10,
            "corruption_type": "Valid verbatim quote on PDF p. 3, but claim invents a dollar deal-value count ($4.5 billion) not on the page",
            "claim_text": "Growth between 2% and 3% backed by $4.5 billion in large deals.",
            "quote": "The new guidance is growth between 2% and 3% in constant currency terms for the full year.",
            "doc_id": "DOC_4",
            "page": 3,
            "claim_kind": "delivered",
            "evaluated_quarter": "Q2 FY26",
        },
        {
            "id": 11,
            "corruption_type": "Number from elsewhere on the SAME page (DOC_4 p. 3 has '21%' in para 4, but cited quote only covers revenue growth '2.2%' and '2.9%')",
            "claim_text": "Q2 FY26 revenue grew 2.2% QoQ and 2.9% YoY with 21% operating margin.",
            "quote": "revenues for the quarter grew 2.2% sequentially and 2.9% year-on-year in constant currency",
            "doc_id": "DOC_4",
            "page": 3,
            "claim_kind": "delivered",
            "evaluated_quarter": "Q2 FY26",
        },
        {
            "id": 12,
            "corruption_type": "Guidance cited from a LATER transcript (Q3 FY26 DOC_3 p. 4 cited as guidance for Q2 FY26 delivery — hindsight chronology violation)",
            "claim_text": "Guided FY26 revenue growth of 3% to 3.5% in constant currency.",
            "quote": "The new revenue growth guidance for this financial year is 3% to 3.5% growth in constant currency",
            "doc_id": "DOC_3",
            "page": 4,
            "claim_kind": "guided",
            "evaluated_quarter": "Q2 FY26",
            "delivered_doc_quarters": ["Q2 FY26"],
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
            claim_kind=tc.get("claim_kind"),
            evaluated_quarter=tc.get("evaluated_quarter"),
            delivered_doc_quarters=tc.get("delivered_doc_quarters"),
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
    from config import DATA_DIR, RESEARCH_DIR, save_json
    from fetch_announcements import create_nse_session
    from generate_research import (
        discover_nse_primary_documents,
        download_and_extract_pages,
    )

    sess = create_nse_session()
    _, infy_docs = discover_nse_primary_documents(sess, "INFY.NS", days_back=460)
    infy_enriched, infy_pages, _ = download_and_extract_pages(sess, "INFY.NS", infy_docs)
    infy_by_id = {d["doc_id"]: d for d in infy_enriched}

    neg_results = run_negative_test_suite(infy_by_id, infy_pages)
    save_json(DATA_DIR / "negative_test_results.json", neg_results)
    print("=== ITEM 2: 12-CLAIM NEGATIVE TEST SUITE ===")
    caught = sum(1 for r in neg_results if r["rejected"])
    for r in neg_results:
        cid = r["id"]
        rej = r["rejected"]
        ctype = r["corruption_type"]
        print(f"Test #{cid:2d} | Rejected={rej} | {ctype}")
        for reason in r["rejection_reasons"]:
            print(f"         -> {reason}")
    print(f"Total negative tests caught: {caught}/12\n")

    print("=== AUDIT OF PREVIOUS v2 CLAIMS UNDER NEW RULES (2a: number-in-quote, 2b: chronology) ===")
    total_pass = 0
    total_rej = 0
    for sym in ["INFY.NS", "RELIANCE.NS", "TCS.NS", "ICICIBANK.NS", "ETERNAL.NS", "PIDILITIND.NS"]:
        _, docs = discover_nse_primary_documents(sess, sym, days_back=460)
        enriched, read_pages, _ = download_and_extract_pages(sess, sym, docs)
        docs_by_id = {d["doc_id"]: d for d in enriched}
        comp_file = RESEARCH_DIR / f"{sym.split('.')[0]}.json"
        res_data = json.loads(comp_file.read_text())
        p_cnt = 0
        r_cnt = 0
        for q in res_data.get("narrative_vs_numbers", {}).get("quarters", []):
            q_name = q.get("quarter")
            deliv_qs = [
                docs_by_id[d_it["doc_id"]]["quarter"]
                for d_it in q.get("delivered", [])
                if d_it.get("doc_id") in docs_by_id
            ]
            for kind, key_txt in [("guided", "guidance"), ("delivered", "actual")]:
                for item in q.get(kind, []):
                    # Extract quote from `source` field ("... — \"quote\"")
                    src_str = item.get("source", "")
                    q_match = re.search(r'—\s*"(.*)"\s*$', src_str, re.DOTALL)
                    quote_str = q_match.group(1) if q_match else ""
                    ok, reasons = verify_single_claim(
                        claim_text=item.get(key_txt, ""),
                        quote=quote_str,
                        doc_id=item.get("doc_id", ""),
                        page=item.get("page"),
                        docs_by_id=docs_by_id,
                        read_pages=read_pages,
                        claim_kind=kind,
                        evaluated_quarter=q_name,
                        delivered_doc_quarters=deliv_qs,
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
    print(f"OVERALL ACROSS 6 COMPANIES (v2 audit): {total_pass} passed, {total_rej} rejected (out of {total_pass + total_rej})")
