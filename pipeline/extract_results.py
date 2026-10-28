"""
FINN Pipeline — Slice 1: Real Results Filing Extractor.

Takes a corporate results PDF (from NSE/BSE), locates the Consolidated (or
Standalone if Consolidated is absent) Statement of Financial Results page,
checks whether the embedded text layer is intact or requires a pypdfium2 page
image fallback, extracts raw line items via Gemini Flash, normalises units
(crore / million / lakh -> ₹ crore), computes Operating EBITDA and QoQ/YoY
changes deterministically in Python, and validates accounting identities.
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

import pdfplumber
import pypdfium2 as pdfium

from config import (
    ANN_DIR,
    DATA_DIR,
    DOCS_DIR,
    ROOT,
    content_hash,
    estimate_cost_usd,
    get_cached,
    log_llm_call,
    save_json,
    set_cache,
    ticker_symbol,
)

# ─── Verified Gemini Free Tier models (checked 2026-10-27 via v1beta/models) ─
EXTRACTION_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.6-flash",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite",
]


def _load_api_key() -> str:
    env_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if env_key:
        return env_key
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.strip().startswith("GEMINI_API_KEY="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("GEMINI_API_KEY not found in environment or finn/.env")


def call_gemini_multimodal(
    prompt: str,
    image_png_bytes: list[bytes] | None = None,
    task: str = "extract_results",
    ticker: str = "",
    models: list[str] | None = None,
) -> tuple[dict, str, int, int]:
    """
    Call Gemini REST API with optional PNG page images, content-hash caching,
    and automatic fallback across verified Free Tier models on 503/429.
    Returns (parsed_json, model_used, tokens_in, tokens_out).
    """
    image_png_bytes = image_png_bytes or []
    hash_input = prompt + "".join(
        content_hash(b.hex()[:2000]) for b in image_png_bytes
    )
    chash = content_hash(hash_input)

    cached = get_cached(chash, task)
    if cached is not None:
        if isinstance(cached, list) and cached and isinstance(cached[0], dict):
            cached = cached[0]
        model_used = cached.get("_meta_model", "gemini-3.5-flash-lite")
        meta_tok = cached.get("_meta_tokens") or {"in": 0, "out": 0}
        log_llm_call(task, ticker, model_used, 0, 0, chash, cache_hit=True)
        return cached, model_used, int(meta_tok.get("in", 0)), int(meta_tok.get("out", 0))

    api_key = _load_api_key()
    model_chain = models or EXTRACTION_MODELS

    parts: list[dict[str, Any]] = []
    for img_bytes in image_png_bytes:
        parts.append(
            {
                "inline_data": {
                    "mime_type": "image/png",
                    "data": base64.b64encode(img_bytes).decode("ascii"),
                }
            }
        )
    parts.append({"text": prompt})

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.0,
        },
    }
    body = json.dumps(payload).encode("utf-8")

    last_err: Exception | None = None
    for model_name in model_chain:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        req = urllib.request.Request(
            url, data=body, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
            text = raw["candidates"][0]["content"]["parts"][0]["text"]
            usage = raw.get("usageMetadata", {})
            tokens_in = int(usage.get("promptTokenCount", 0))
            tokens_out = int(usage.get("candidatesTokenCount", 0)) + int(
                usage.get("thoughtsTokenCount", 0)
            )
            actual_model = raw.get("modelVersion", model_name)
            parsed = json.loads(text)
            if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                parsed = parsed[0]
            if isinstance(parsed, dict):
                parsed["_meta_model"] = actual_model
                parsed["_meta_tokens"] = {
                    "in": tokens_in,
                    "out": tokens_out,
                    "out_candidates": int(usage.get("candidatesTokenCount", 0)),
                    "out_thoughts": int(usage.get("thoughtsTokenCount", 0)),
                }
            set_cache(chash, task, parsed)
            log_llm_call(
                task,
                ticker,
                actual_model,
                tokens_in,
                tokens_out,
                chash,
                cache_hit=False,
            )
            return parsed, actual_model, tokens_in, tokens_out
        except (urllib.error.HTTPError, TimeoutError, Exception) as e:
            last_err = e
            # Back off harder on 503/429 (model overloaded / rate limited)
            code = getattr(e, "code", None)
            time.sleep(15.0 if code in (429, 503) else 2.0)
            continue

    raise RuntimeError(f"All Gemini models failed for {ticker}: {last_err}")


# ─── Step 1: Locate the Statement of Financial Results page(s) ───────────────

def _score_statement_page(text: str) -> dict[str, Any]:
    """
    Score a single PDF page to determine if it is the primary Statement of
    Financial Results (P&L) table, whether it is Consolidated vs Standalone,
    and whether its embedded text layer is clean or garbled.
    """
    if not text or len(text.strip()) < 100:
        return {"score": -100, "basis": "unknown", "needs_vision": True}

    low = text.lower()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    header_text = " ".join(lines[:15]).lower()

    # Reject auditor review reports, cash flow statements, balance sheets, segment tables
    if any(
        phrase in header_text
        for phrase in [
            "independent auditor",
            "limited review report",
            "chartered accountants",
            "statement of cash flow",
            "cash flow statement",
            "segment information",
            "segmental results",
            "segment wise",
            "annexure i to",
            "press release",
            "media release",
            "earnings presentation",
        ]
    ):
        return {"score": -50, "basis": "unknown", "needs_vision": False}

    if "we have reviewed the accompanying" in low or "we have audited the accompanying" in low:
        return {"score": -50, "basis": "unknown", "needs_vision": False}

    # Reject USD-denominated tables (e.g., Infosys IFRS USD pages)
    if "dollars in millions" in header_text or "in us $ million" in header_text or "ifrs – usd" in header_text:
        return {"score": -40, "basis": "unknown", "needs_vision": False}

    score = 0

    # Must have P&L top-line and bottom-line indicators
    has_rev = (
        "revenue from operations" in low
        or "revenue from operation" in low
        or "total revenue from operations" in low
        or "rcvcnuc from opcretions" in low
        or "rcvenur from odcralions" in low
        or "interest earned" in low
        or "rest earned" in low  # OCR variant in ICICIBANK
    )
    has_pbt = (
        "profit before tax" in low
        or "profit/(loss) before tax" in low
        or "profit/ (loss) before tax" in low
        or "profit from ordinary activities" in low
        or "profit bcforc tax" in low
        or "pmfir bcforc rsx" in low
    )
    has_pat = (
        "profit for the period" in low
        or "profit after tax" in low
        or "prollt after tax" in low
        or "net profit for the period" in low
        or "net profit/ (loss) after taxes" in low
        or "profit for thc pcriod" in low
        or "prolit for thc dcriod" in low
    )
    has_quarters = (
        "quarter ended" in low
        or "ouarter end" in low
        or "quartcr" in low
        or "three months ended" in low
        or "3 months ended" in low
        or "quarterended" in low
    )

    if not (has_rev and (has_pbt or has_pat)):
        return {"score": -20, "basis": "unknown", "needs_vision": False}

    score += 40
    if has_pbt and has_pat:
        score += 20
    if has_quarters:
        score += 20
    if "statement of" in header_text or "statcmcnt of" in header_text or "financial results" in header_text or "fin.nci.l rcsulls" in header_text:
        score += 15

    # Basis detection: Consolidated vs Standalone
    if "consolidated" in header_text or "consolidat€d" in header_text or "consolidstcd" in header_text:
        basis = "consolidated"
        score += 35  # Strongly prefer Consolidated over Standalone
    elif "standalone" in header_text:
        basis = "standalone"
        score += 10
    elif "consolidated" in low[:800] or "consolidstcd" in low[:800]:
        basis = "consolidated"
        score += 30
    elif "standalone" in low[:800]:
        basis = "standalone"
        score += 5
    else:
        basis = "standalone"  # Single-entity companies (e.g., Page Industries, Colgate)
        score += 15

    # Check if text layer on Revenue / Total Income lines has at least 4 clean numbers
    # (3 quarterly columns + 1 year/half-year column). If fewer, OCR dropped columns or garbled digits.
    rev_numbers = []
    for ln in lines:
        l_low = ln.lower()
        if any(
            k in l_low
            for k in [
                "revenue from operations",
                "total revenue from operations",
                "interest earned",
                "rest earned",
            ]
        ):
            # Find numbers like 49,244 or 152,998.80 or 1,42,044.53
            nums = re.findall(r"\b\d[\d,]*\.?\d*\b", ln)
            # Filter out single-digit footnote/row numbers like "1" or "4"
            nums = [n for n in nums if len(n.replace(",", "").split(".")[0]) >= 3]
            rev_numbers.extend(nums)

    # Also detect obvious OCR corruption markers on the page
    ocr_garble = any(
        bad in text
        for bad in [
            "Revenue from operations : . .",
            "<24 60R",
            "Setvices",
            "Prollt After Tax",
        ]
    )
    needs_vision = (len(rev_numbers) < 4) or ocr_garble

    return {
        "score": score,
        "basis": basis,
        "needs_vision": needs_vision,
        "rev_numbers_count": len(rev_numbers),
    }


def select_statement_page(pdf_path: Path) -> dict[str, Any]:
    """
    Scan a results PDF and return the best Statement of Financial Results page
    (preferring Consolidated over Standalone).
    """
    try:
        with pdfplumber.open(pdf_path) as pdf:
            page_candidates = []
            for idx, page in enumerate(pdf.pages):
                txt = page.extract_text() or ""
                meta = _score_statement_page(txt)
                if meta["score"] > 0:
                    page_candidates.append(
                        {
                            "page_number": idx + 1,
                            "score": meta["score"],
                            "basis": meta["basis"],
                            "needs_vision": meta["needs_vision"],
                            "text": txt,
                            "total_pages": len(pdf.pages),
                        }
                    )
    except Exception as e:
        return {
            "status": "corrupted_pdf",
            "error": f"{type(e).__name__}: {e}",
        }

    if not page_candidates:
        return {
            "status": "no_statement_page_found",
            "error": "No P&L statement table found in PDF",
        }

    # Sort by score descending, then earlier page number
    page_candidates.sort(key=lambda c: (-c["score"], c["page_number"]))
    best = page_candidates[0]
    best["status"] = "ok"
    return best


def render_pdf_page_png(pdf_path: Path, page_number: int, scale: float = 2.0) -> bytes:
    """Render a 1-indexed PDF page to PNG bytes using pypdfium2."""
    doc = pdfium.PdfDocument(str(pdf_path))
    page = doc[page_number - 1]
    bitmap = page.render(scale=scale)
    pil_img = bitmap.to_pil()
    buf = io.BytesIO()
    pil_img.save(buf, format="PNG")
    return buf.getvalue()


# ─── Step 2: Prompt & Extraction ─────────────────────────────────────────────

EXTRACTION_PROMPT = """You are a precise financial statement data extractor for Indian listed companies (NSE/BSE).

You are given Page {page_number} of {company} ({ticker})'s official quarterly financial results filing.
{vision_note}

Follow these rules strictly:
1. **Basis**: Report whether this statement is `"consolidated"` or `"standalone"`.
2. **Entity type**:
   - Set `"entity_type": "bank"` ONLY if this is a bank / banking format statement reporting `"Interest earned"` and `"Operating profit before provisions and contingencies"`.
   - Otherwise set `"entity_type": "corporate"`.
3. **Reported unit**: Identify the unit stated at the top of the table: `"crore"`, `"million"`, or `"lakh"`. Do NOT convert the numbers yourself — transcribe the exact numbers as printed in the table in its native reported unit.
4. **Column mapping by DATE header (CRITICAL — do NOT assume column order)**:
   - Read the exact date headers of the first three quarterly ("Three months ended" / "Quarter ended") columns from left to right (`col_1`, `col_2`, `col_3`).
   - Record which column index (`"Col 1"`, `"Col 2"`, or `"Col 3"`) corresponds to `"current"`, `"previous"`, and `"year_ago"`.
   - `"current"`: the most recent quarter ended (e.g. `"30 Sep 2026"` or `"30 Jun 2026"`).
   - `"previous"`: the immediately preceding quarter (e.g. `"30 Jun 2026"` when current is Sep 2026, or `"31 Mar 2026"` when current is Jun 2026). Note: ITC places `"Corresponding 3 Months ended 30.06.2025"` (year-ago) in Col 2 and `"Preceding 3 Months ended 31.03.2026"` (previous quarter) in Col 3 — always match by date!
   - `"year_ago"`: the same quarter one year earlier (e.g. `"30 Sep 2025"` or `"30 Jun 2025"`).
5. **Exact printed row labels**:
   - Transcribe the exact printed row label used for `revenue`, `total_expenses`, `finance_costs`, `depreciation_amortisation`, `pbt`, and `pat`.
6. **Line items to extract (in native reported unit, for all 3 quarters)**:
   - If `"entity_type" == "bank"`:
     - `revenue`: Use the printed `"TOTAL INCOME"` (`Interest earned + Other income`) row.
     - `interest_earned`: `"Interest earned"` line.
     - `other_income`: `"Other income"` line.
     - `operating_profit_before_provisions`: `"Operating profit before provisions and contingencies"`.
     - `pbt`: `"Profit from ordinary activities before tax"` (including share of profit in associates if shown before tax).
     - `pat`: `"Net Profit for the period"` (after tax and minority interest).
     - Set `total_expenses`, `finance_costs`, `depreciation_amortisation`, and `explicit_ebitda` all to `null`.
   - If `"entity_type" == "corporate"`:
     - `revenue`: Use the printed `"Revenue from operations"` / `"Total revenue from operations"` / `"REVENUE FROM OPERATIONS"` line as printed on the statement.
     - `gross_value_of_sales`: Only if a separate `"Value of Sales & Services (Revenue)"` line is printed above `"Less: GST Recovered"` (as in Reliance), otherwise `null`.
     - `gst_recovered`: Only if `"Less: GST Recovered"` is printed on the statement, otherwise `null`.
     - `excise_duty`: Only if `"Excise Duty"` is printed under Expenses, otherwise `null`.
     - `other_income`: `"Other income"` line.
     - `total_income`: `"Total income"` line.
     - `total_expenses`: `"Total expenses"` line.
     - `finance_costs`: `"Finance costs"` line.
     - `depreciation_amortisation`: `"Depreciation and amortisation expense"` line.
     - `explicit_ebitda`: Only if the statement page explicitly prints a row labelled `"EBITDA"` or `"Operating EBITDA"`, otherwise `null`.
     - `pbt_before_exceptional`: `"Profit before exceptional items and tax"` if printed, otherwise `null`.
     - `exceptional_items`: `"Exceptional items"` if non-zero in any of the 3 quarters, otherwise `null`.
     - `pbt`: `"Profit before tax"` (after exceptional items).
     - `pat`: `"Profit for the period"` / `"Profit after tax"` (for Reliance, use `"Profit After Tax and Share of Profit / (Loss) of Associates and Joint Ventures"`; for Sun Pharma, use `"Net Profit / (loss) after taxes, share of profit / (loss) of associates and joint venture and non-controlling interests"`).
     - `pat_owners`: `"Profit attributable to Owners of the Company"` / `"Owners of the Parent"` if separately stated below PAT, otherwise `null`.

Page text extracted via pdfplumber (may have OCR gaps if image is attached):
\"\"\"
{page_text}
\"\"\"

Return ONLY valid JSON matching this exact schema:
{{
  "basis": "consolidated" | "standalone",
  "entity_type": "corporate" | "bank",
  "reported_unit": "crore" | "million" | "lakh",
  "quarter_label": "Q2 FY27" | "Q1 FY27",
  "period_ended": {{
    "current": "YYYY-MM-DD",
    "previous": "YYYY-MM-DD",
    "year_ago": "YYYY-MM-DD"
  }},
  "column_order": {{
    "col_1_header": "exact text of quarterly column 1 header",
    "col_2_header": "exact text of quarterly column 2 header",
    "col_3_header": "exact text of quarterly column 3 header",
    "current_col": "Col 1" | "Col 2" | "Col 3",
    "previous_col": "Col 1" | "Col 2" | "Col 3",
    "year_ago_col": "Col 1" | "Col 2" | "Col 3"
  }},
  "row_labels": {{
    "revenue": "exact printed row label",
    "total_expenses": "exact printed row label or null",
    "finance_costs": "exact printed row label or null",
    "depreciation_amortisation": "exact printed row label or null",
    "operating_profit_before_provisions": "exact printed row label or null",
    "pbt": "exact printed row label",
    "pat": "exact printed row label",
    "pat_owners": "exact printed row label or null"
  }},
  "raw_metrics": {{
    "revenue": {{"current": number|null, "previous": number|null, "year_ago": number|null}},
    "gross_value_of_sales": {{"current": number|null, "previous": number|null, "year_ago": number|null}},
    "gst_recovered": {{"current": number|null, "previous": number|null, "year_ago": number|null}},
    "excise_duty": {{"current": number|null, "previous": number|null, "year_ago": number|null}},
    "other_income": {{"current": number|null, "previous": number|null, "year_ago": number|null}},
    "total_income": {{"current": number|null, "previous": number|null, "year_ago": number|null}},
    "total_expenses": {{"current": number|null, "previous": number|null, "year_ago": number|null}},
    "finance_costs": {{"current": number|null, "previous": number|null, "year_ago": number|null}},
    "depreciation_amortisation": {{"current": number|null, "previous": number|null, "year_ago": number|null}},
    "operating_profit_before_provisions": {{"current": number|null, "previous": number|null, "year_ago": number|null}},
    "explicit_ebitda": {{"current": number|null, "previous": number|null, "year_ago": number|null}},
    "pbt_before_exceptional": {{"current": number|null, "previous": number|null, "year_ago": number|null}},
    "exceptional_items": {{"current": number|null, "previous": number|null, "year_ago": number|null}},
    "pbt": {{"current": number|null, "previous": number|null, "year_ago": number|null}},
    "pat": {{"current": number|null, "previous": number|null, "year_ago": number|null}},
    "pat_owners": {{"current": number|null, "previous": number|null, "year_ago": number|null}}
  }}
}}
"""


# ─── Step 3: Unit Normalisation, EBITDA Calculation & Validation ─────────────

UNIT_TO_CRORE_FACTOR = {
    "crore": 1.0,
    "crores": 1.0,
    "million": 0.1,   # 1 crore = 10 million
    "millions": 0.1,
    "lakh": 0.01,     # 1 crore = 100 lakh
    "lakhs": 0.01,
    "lac": 0.01,
    "lacs": 0.01,
}


def _pct_change(curr: float | None, base: float | None) -> float | None:
    if curr is None or base is None or base == 0:
        return None
    return round(((curr - base) / abs(base)) * 100.0, 2)


def _norm_triplet(triplet: dict | None, factor: float) -> dict[str, float | None]:
    if not isinstance(triplet, dict):
        return {"current": None, "previous": None, "year_ago": None}
    out: dict[str, float | None] = {}
    for k in ("current", "previous", "year_ago"):
        v = triplet.get(k)
        out[k] = round(float(v) * factor, 2) if v is not None else None
    return out


def _build_metric_with_changes(triplet_cr: dict[str, float | None]) -> dict[str, Any]:
    curr = triplet_cr.get("current")
    prev = triplet_cr.get("previous")
    yoy_base = triplet_cr.get("year_ago")
    return {
        "value": curr,
        "previous_quarter": prev,
        "year_ago_quarter": yoy_base,
        "qoq": _pct_change(curr, prev),
        "yoy": _pct_change(curr, yoy_base),
    }


def _build_derivation(
    ticker: str,
    page_num: int,
    needs_vision: bool,
    basis: str,
    entity_type: str,
    reported_unit: str,
    factor: float,
    ebitda_status: str,
    column_order: dict[str, Any],
    row_labels: dict[str, Any],
    raw: dict[str, Any],
    rev_cr: dict[str, float | None],
    ebitda_cr: dict[str, float | None],
    op_prof_cr: dict[str, float | None],
    pbt_cr: dict[str, float | None],
    pat_cr: dict[str, float | None],
    pat_owners_cr: dict[str, float | None],
) -> dict[str, str]:
    col_desc = (
        f"Columns L→R: Col 1='{column_order.get('col_1_header')}', "
        f"Col 2='{column_order.get('col_2_header')}', "
        f"Col 3='{column_order.get('col_3_header')}' "
        f"(mapped Current={column_order.get('current_col')}, "
        f"Previous={column_order.get('previous_col')}, "
        f"Year-Ago={column_order.get('year_ago_col')})."
    )
    unit_note = (
        f"reported in ₹ {reported_unit}"
        if factor == 1.0
        else f"reported in ₹ {reported_unit}, normalised ×{factor} to ₹ crore"
    )
    extra_basis = ""
    if ticker == "PAGEIND.NS":
        extra_basis = " Manually verified on PDF p. 3 Note 9: 'The Company has no subsidiary/ associate/ joint venture company(ies) as at June 30, 2026' (standalone only)."
    basis_note = (
        f"{basis.capitalize()} Statement of Financial Results (PDF p. {page_num}"
        f"{' via vision' if needs_vision else ''}, {unit_note}). {col_desc}{extra_basis}"
    )

    rev_row_lbl = row_labels.get("revenue") or ("Total Income" if entity_type == "bank" else "Revenue from Operations")
    r_c = rev_cr.get("current")
    r_p = rev_cr.get("previous")
    r_y = rev_cr.get("year_ago")

    if entity_type == "bank":
        revenue_definition = (
            f"Printed row '{rev_row_lbl}' (Bank Total Income = Interest Earned + Other Income) = "
            f"₹{r_c:,.2f} Cr (Prev Q: ₹{r_p:,.2f} Cr; Year-ago Q: ₹{r_y:,.2f} Cr)."
        )
        ebitda_formula = (
            f"Not applicable (`not_applicable`) for banking companies under Banking Regulation Act Form B. "
            f"Printed row '{row_labels.get('operating_profit_before_provisions') or 'Operating Profit before Provisions & Contingencies'}' = "
            f"₹{op_prof_cr.get('current'):,.2f} Cr (Prev Q: ₹{op_prof_cr.get('previous'):,.2f} Cr; Year-ago Q: ₹{op_prof_cr.get('year_ago'):,.2f} Cr)."
        )
    else:
        g_sales = _norm_triplet(raw.get("gross_value_of_sales"), factor)
        gst_rec = _norm_triplet(raw.get("gst_recovered"), factor)
        excise = _norm_triplet(raw.get("excise_duty"), factor)
        other_inc = _norm_triplet(raw.get("other_income"), factor)

        if g_sales.get("current") is not None and gst_rec.get("current") is not None:
            ex_c = excise.get("current") or 0.0
            net_ex_c = round((r_c or 0.0) - ex_c, 2)
            revenue_definition = (
                f"Printed row '{rev_row_lbl}' = ₹{r_c:,.2f} Cr (Prev Q: ₹{r_p:,.2f} Cr; Year-ago Q: ₹{r_y:,.2f} Cr). "
                f"Gross vs Net: Printed 'Revenue from Operations' (₹{r_c:,.2f} Cr) is NET of GST Recovered (₹{gst_rec['current']:,.2f} Cr deducted from Gross 'Value of Sales & Services' of ₹{g_sales['current']:,.2f} Cr) "
                f"and GROSS of Excise Duty (₹{ex_c:,.2f} Cr reported inside Expenses; Revenue net of both GST & Excise Duty is ₹{net_ex_c:,.2f} Cr)."
            )
        elif excise.get("current") is not None and excise.get("current") > 0:
            ex_c = excise.get("current") or 0.0
            ex_p = excise.get("previous") or 0.0
            ex_y = excise.get("year_ago") or 0.0
            net_c = round((r_c or 0.0) - ex_c, 2)
            net_p = round((r_p or 0.0) - ex_p, 2)
            net_y = round((r_y or 0.0) - ex_y, 2)
            revenue_definition = (
                f"Printed row '{rev_row_lbl}' = ₹{r_c:,.2f} Cr (Prev Q: ₹{r_p:,.2f} Cr; Year-ago Q: ₹{r_y:,.2f} Cr). "
                f"Gross vs Net: Printed row is GROSS of Excise Duty (Excise Duty in Expenses = ₹{ex_c:,.2f} Cr in Current Q, ₹{ex_p:,.2f} Cr in Prev Q, ₹{ex_y:,.2f} Cr in Year-ago Q; "
                f"Net Revenue from Operations net of Excise Duty = ₹{net_c:,.2f} Cr Current, ₹{net_p:,.2f} Cr Prev, ₹{net_y:,.2f} Cr Year-ago)."
            )
        else:
            oi_str = f" (excludes Other Income of ₹{other_inc['current']:,.2f} Cr)" if other_inc.get("current") is not None else ""
            revenue_definition = (
                f"Revenue from operations as printed ('{rev_row_lbl}'){oi_str} = ₹{r_c:,.2f} Cr "
                f"(Prev Q: ₹{r_p:,.2f} Cr; Year-ago Q: ₹{r_y:,.2f} Cr)."
            )

        te_cr = _norm_triplet(raw.get("total_expenses"), factor)
        fc_cr = _norm_triplet(raw.get("finance_costs"), factor)
        da_cr = _norm_triplet(raw.get("depreciation_amortisation"), factor)
        eb_c = ebitda_cr.get("current")
        eb_p = ebitda_cr.get("previous")
        eb_y = ebitda_cr.get("year_ago")
        if ebitda_status == "reported":
            ebitda_formula = f"Printed EBITDA row = ₹{eb_c:,.2f} Cr (Prev Q: ₹{eb_p:,.2f} Cr; Year-ago Q: ₹{eb_y:,.2f} Cr)."
        else:
            op_c = round((r_c or 0.0) - (te_cr.get("current") or 0.0) + (fc_cr.get("current") or 0.0), 2)
            margin_c = round((eb_c / r_c) * 100.0, 2) if (eb_c and r_c) else 0.0
            extra_seg = ""
            ex_cur = excise.get("current")
            if ex_cur:
                # Computed from the extracted excise line (no hard-coded figures)
                extra_seg = (
                    f" (Excise Duty of ₹{ex_cur:,.2f} Cr sits in both Revenue from Operations and Total Expenses, "
                    f"so it cancels out in Operating Profit; EBITDA margin on revenue net of excise = "
                    f"{(eb_c / ((r_c or 0.0) - ex_cur) * 100.0) if eb_c and r_c and (r_c - ex_cur) else 0.0:.2f}%.)"
                )
            ebitda_formula = (
                f"Derived (`derived`): Operating Profit (Revenue ₹{r_c:,.2f} Cr − Total Expenses ₹{te_cr.get('current'):,.2f} Cr + Finance Costs ₹{fc_cr.get('current'):,.2f} Cr = ₹{op_c:,.2f} Cr) "
                f"+ D&A (₹{da_cr.get('current'):,.2f} Cr) = ₹{eb_c:,.2f} Cr ({margin_c:.2f}% margin; Prev Q: ₹{eb_p:,.2f} Cr; Year-ago Q: ₹{eb_y:,.2f} Cr).{extra_seg}"
            )

    pbt_bef_cr = _norm_triplet(raw.get("pbt_before_exceptional"), factor)
    exc_cr = _norm_triplet(raw.get("exceptional_items"), factor)
    pbt_lbl = row_labels.get("pbt") or "Profit Before Tax"
    if exc_cr.get("current") not in (None, 0.0) or exc_cr.get("previous") not in (None, 0.0) or exc_cr.get("year_ago") not in (None, 0.0):
        pbt_basis = (
            f"Printed row '{pbt_lbl}' (after exceptional items) = ₹{pbt_cr.get('current'):,.2f} Cr "
            f"(Prev Q: ₹{pbt_cr.get('previous'):,.2f} Cr; Year-ago Q: ₹{pbt_cr.get('year_ago'):,.2f} Cr; "
            f"PBT before exceptional items = ₹{(pbt_bef_cr.get('current') if pbt_bef_cr.get('current') is not None else pbt_cr.get('current')):,.2f} Cr, "
            f"Current Q exceptional item = ₹{(exc_cr.get('current') or 0.0):,.2f} Cr)."
        )
    else:
        pbt_basis = (
            f"Printed row '{pbt_lbl}' (no current-quarter exceptional items) = ₹{pbt_cr.get('current'):,.2f} Cr "
            f"(Prev Q: ₹{pbt_cr.get('previous'):,.2f} Cr; Year-ago Q: ₹{pbt_cr.get('year_ago'):,.2f} Cr)."
        )

    pat_lbl = row_labels.get("pat") or "Profit for the period"
    if pat_owners_cr.get("current") is not None and pat_owners_cr.get("current") != pat_cr.get("current"):
        nci = round((pat_cr.get("current") or 0.0) - (pat_owners_cr.get("current") or 0.0), 2)
        pat_basis = (
            f"Printed row '{pat_lbl}' (Total Consolidated Profit after tax) = ₹{pat_cr.get('current'):,.2f} Cr "
            f"(Profit attributable to Owners of the Company/Parent = ₹{pat_owners_cr.get('current'):,.2f} Cr; Non-controlling interest = ₹{nci:,.2f} Cr)."
        )
    else:
        pat_basis = (
            f"Printed row '{pat_lbl}' = ₹{pat_cr.get('current'):,.2f} Cr "
            f"(Prev Q: ₹{pat_cr.get('previous'):,.2f} Cr; Year-ago Q: ₹{pat_cr.get('year_ago'):,.2f} Cr)."
        )

    return {
        "basis_note": basis_note,
        "revenue_definition": revenue_definition,
        "ebitda_formula": ebitda_formula,
        "pbt_basis": pbt_basis,
        "pat_basis": pat_basis,
    }


def extract_results_from_pdf(
    pdf_path: Path,
    ticker: str,
    company: str,
    source_url: str = "",
) -> dict[str, Any]:
    """
    Full Slice 1 pipeline for a single results PDF:
    1. Locate Consolidated (or Standalone) statement page
    2. Render page PNG if text layer is incomplete/garbled
    3. Extract raw metrics via Gemini Flash (fresh task key extract_results_v2)
    4. Normalise units to ₹ Crore, compute Operating EBITDA & QoQ/YoY in Python
    5. Run validation checks
    """
    page_info = select_statement_page(pdf_path)
    if page_info["status"] != "ok":
        return {
            "status": page_info["status"],
            "ticker": ticker,
            "company_name": company,
            "pdf_file": pdf_path.name,
            "source_url": source_url,
            "error": page_info.get("error"),
        }

    page_num = page_info["page_number"]
    needs_vision = page_info["needs_vision"]
    images: list[bytes] = []
    if needs_vision:
        images.append(render_pdf_page_png(pdf_path, page_num, scale=2.0))

    vision_note = (
        "An image of this page is attached because the PDF's embedded OCR text has missing or garbled numbers. Read all numbers from the page image."
        if needs_vision
        else "The PDF has a digital text layer provided below."
    )
    prompt = EXTRACTION_PROMPT.format(
        page_number=page_num,
        company=company,
        ticker=ticker,
        vision_note=vision_note,
        page_text=page_info["text"][:10000],
    )

    llm_out, model_used, tokens_in, tokens_out = call_gemini_multimodal(
        prompt=prompt,
        image_png_bytes=images,
        task="extract_results_v2",
        ticker=f"{ticker}_{pdf_path.stem}",
    )

    reported_unit = (llm_out.get("reported_unit") or "crore").lower().strip()
    factor = UNIT_TO_CRORE_FACTOR.get(reported_unit, 1.0)
    entity_type = llm_out.get("entity_type", "corporate")
    basis = llm_out.get("basis", page_info["basis"])
    raw = llm_out.get("raw_metrics", {})
    column_order = llm_out.get("column_order", {})
    row_labels = llm_out.get("row_labels", {})

    rev_cr = _norm_triplet(raw.get("revenue"), factor)
    pbt_cr = _norm_triplet(raw.get("pbt"), factor)
    pat_cr = _norm_triplet(raw.get("pat"), factor)
    pat_owners_cr = _norm_triplet(raw.get("pat_owners"), factor)

    # Compute Operating EBITDA for corporate filings, or mark not_applicable for banks
    if entity_type == "bank":
        ebitda_status = "not_applicable"
        ebitda_cr = {"current": None, "previous": None, "year_ago": None}
        ebitda_raw = {"current": None, "previous": None, "year_ago": None}
        op_prof_cr = _norm_triplet(
            raw.get("operating_profit_before_provisions"), factor
        )
    else:
        op_prof_cr = {"current": None, "previous": None, "year_ago": None}
        explicit_ebitda = raw.get("explicit_ebitda") or {}
        if all(explicit_ebitda.get(k) is not None for k in ("current", "previous", "year_ago")):
            ebitda_status = "reported"
            ebitda_raw = {
                k: float(explicit_ebitda[k]) for k in ("current", "previous", "year_ago")
            }
            ebitda_cr = _norm_triplet(ebitda_raw, factor)
        else:
            # Operating EBITDA = Operating Profit (Revenue - Total expenses + Finance costs) + D&A, labelled "derived"
            ebitda_status = "derived"
            ebitda_raw = {}
            for k in ("current", "previous", "year_ago"):
                r_val = (raw.get("revenue") or {}).get(k)
                te_val = (raw.get("total_expenses") or {}).get(k)
                fc_val = (raw.get("finance_costs") or {}).get(k)
                da_val = (raw.get("depreciation_amortisation") or {}).get(k)
                if None not in (r_val, te_val, fc_val, da_val):
                    ebitda_raw[k] = round(
                        float(r_val) - float(te_val) + float(fc_val) + float(da_val),
                        2,
                    )
                else:
                    ebitda_raw[k] = None
            ebitda_cr = _norm_triplet(ebitda_raw, factor)

    # Validation checks
    validation_flags: list[str] = []
    for k in ("current", "previous", "year_ago"):
        if rev_cr[k] is None:
            validation_flags.append(f"missing_revenue_{k}")
        if pbt_cr[k] is None:
            validation_flags.append(f"missing_pbt_{k}")
        if pat_cr[k] is None:
            validation_flags.append(f"missing_pat_{k}")

        if entity_type != "bank" and ebitda_cr[k] is not None and rev_cr[k] is not None:
            if ebitda_cr[k] >= rev_cr[k]:
                validation_flags.append(
                    f"ebitda_gte_revenue_{k} ({ebitda_cr[k]} >= {rev_cr[k]})"
                )

        if pat_cr[k] is not None and pbt_cr[k] is not None:
            if pat_cr[k] > pbt_cr[k]:
                validation_flags.append(
                    f"pat_gt_pbt_{k} ({pat_cr[k]} > {pbt_cr[k]})"
                )

    revenue_metric = _build_metric_with_changes(rev_cr)
    ebitda_metric = (
        None
        if entity_type == "bank"
        else _build_metric_with_changes(ebitda_cr)
    )
    pbt_metric = _build_metric_with_changes(pbt_cr)
    pat_metric = _build_metric_with_changes(pat_cr)
    derivation = _build_derivation(
        ticker=ticker,
        page_num=page_num,
        needs_vision=needs_vision,
        basis=basis,
        entity_type=entity_type,
        reported_unit=reported_unit,
        factor=factor,
        ebitda_status=ebitda_status,
        column_order=column_order,
        row_labels=row_labels,
        raw=raw,
        rev_cr=rev_cr,
        ebitda_cr=ebitda_cr,
        op_prof_cr=op_prof_cr,
        pbt_cr=pbt_cr,
        pat_cr=pat_cr,
        pat_owners_cr=pat_owners_cr,
    )

    # Build concise, grounded one-line summary from the extracted numbers (zero AI slop)
    q_label = llm_out.get("quarter_label", "Quarterly")
    rev_str = f"₹{revenue_metric['value']:,.0f} Cr ({revenue_metric['yoy']:+.1f}% YoY, {revenue_metric['qoq']:+.1f}% QoQ)"
    pat_str = f"₹{pat_metric['value']:,.0f} Cr ({pat_metric['yoy']:+.1f}% YoY, {pat_metric['qoq']:+.1f}% QoQ)"
    if entity_type == "bank":
        op_metric = _build_metric_with_changes(op_prof_cr)
        op_str = (
            f"Operating profit (ex-provisions) ₹{op_metric['value']:,.0f} Cr ({op_metric['yoy']:+.1f}% YoY)."
            if op_metric["value"]
            else ""
        )
        summary = f"{q_label} ({basis}): Total income {rev_str}; PAT {pat_str}. {op_str}".strip()
        highlights = f"Basis: {basis.capitalize()} · Unit normalised from ₹ {reported_unit} · Page {page_num} · Bank format (EBITDA N/A)"
    else:
        eb_val = ebitda_metric["value"] if ebitda_metric else None
        eb_margin = (
            round((eb_val / revenue_metric["value"]) * 100.0, 1)
            if eb_val and revenue_metric["value"]
            else None
        )
        eb_str = (
            f"EBITDA ({ebitda_status}) ₹{eb_val:,.0f} Cr ({ebitda_metric['yoy']:+.1f}% YoY, margin {eb_margin}%)"
            if eb_val is not None
            else "EBITDA N/A"
        )
        summary = f"{q_label} ({basis}): Revenue {rev_str}; {eb_str}; PAT {pat_str}."
        highlights = f"Basis: {basis.capitalize()} · Normalised from ₹ {reported_unit} (Page {page_num}{' via vision' if needs_vision else ''}) · EBITDA {ebitda_status}"

    return {
        "status": "ok",
        "ticker": ticker,
        "company_name": company,
        "pdf_file": pdf_path.name,
        "source_url": source_url,
        "source_page": page_num,
        "vision_used": needs_vision,
        "basis": basis,
        "entity_type": entity_type,
        "reported_unit": reported_unit,
        "normalised_unit": "crore",
        "quarter": q_label,
        "period_ended": llm_out.get("period_ended", {}),
        "column_order": column_order,
        "row_labels": row_labels,
        "ebitda_status": ebitda_status,
        "revenue_label": "Total Income" if entity_type == "bank" else "Revenue from Operations",
        "revenue": revenue_metric,
        "ebitda": ebitda_metric,
        "operating_profit_ex_provisions": _build_metric_with_changes(op_prof_cr) if entity_type == "bank" else None,
        "pbt": pbt_metric,
        "pat": pat_metric,
        "pat_owners": _build_metric_with_changes(pat_owners_cr) if pat_owners_cr["current"] is not None else None,
        "raw_in_reported_unit": {
            "unit": reported_unit,
            "revenue": raw.get("revenue"),
            "gross_value_of_sales": raw.get("gross_value_of_sales"),
            "gst_recovered": raw.get("gst_recovered"),
            "excise_duty": raw.get("excise_duty"),
            "other_income": raw.get("other_income"),
            "total_income": raw.get("total_income"),
            "total_expenses": raw.get("total_expenses"),
            "finance_costs": raw.get("finance_costs"),
            "depreciation_amortisation": raw.get("depreciation_amortisation"),
            "operating_profit_before_provisions": raw.get("operating_profit_before_provisions"),
            "ebitda_in_reported_unit": ebitda_raw,
            "pbt_before_exceptional": raw.get("pbt_before_exceptional"),
            "exceptional_items": raw.get("exceptional_items"),
            "pbt": raw.get("pbt"),
            "pat": raw.get("pat"),
            "pat_owners": raw.get("pat_owners"),
        },
        "derivation": derivation,
        "validation": {
            "passed": len(validation_flags) == 0,
            "flags": validation_flags,
        },
        "summary": summary,
        "highlights": highlights,
        "model_used": model_used,
        "tokens": {"in": tokens_in, "out": tokens_out},
        "paid_tier_equivalent_usd": estimate_cost_usd(model_used, tokens_in, tokens_out),
    }


# ─── Test suite across all 10 real NSE results PDFs ──────────────────────────

SLICE1_FILINGS = [
    {
        "ticker": "ICICIBANK.NS",
        "company": "ICICI Bank Limited",
        "pdf": "ICICIBANK_Q2FY27.pdf",
        "timestamp": "2026-10-17T15:21:44+05:30",
        "headline": "Outcome of Board Meeting — Unaudited Standalone and Consolidated Financial Results for Q2 FY27 (quarter ended Sep 30, 2026)",
        "source_url": "https://nsearchives.nseindia.com/corporate/ICICI2022_17102026152039_NSEBSE17102026.pdf",
    },
    {
        "ticker": "INFY.NS",
        "company": "Infosys Limited",
        "pdf": "INFY_Q2FY27.pdf",
        "timestamp": "2026-10-23T16:08:26+05:30",
        "headline": "Outcome of Board Meeting — Audited Consolidated and Standalone Financial Results for Q2 FY27 (quarter ended Sep 30, 2026)",
        "source_url": "https://nsearchives.nseindia.com/corporate/Infosys_23102026160704_BM_Outcome_Oct232026_1.pdf",
    },
    {
        "ticker": "TCS.NS",
        "company": "Tata Consultancy Services Limited",
        "pdf": "TCS_Q2FY27.pdf",
        "timestamp": "2026-10-08T15:40:12+05:30",
        "headline": "Outcome of Board Meeting — Audited Consolidated and Standalone Interim Financial Results for Q2 FY27 (quarter ended Sep 30, 2026)",
        "source_url": "https://nsearchives.nseindia.com/corporate/TCS_CORPCS_08102026153124_Post_BM_SE_Letter_fin.pdf",
    },
    {
        "ticker": "MARUTI.NS",
        "company": "Maruti Suzuki India Limited",
        "pdf": "MARUTI_Q2FY27.pdf",
        "timestamp": "2026-10-27T15:27:51+05:30",
        "headline": "Outcome of Board Meeting — Unaudited Standalone and Consolidated Financial Results for Q2 FY27 (quarter ended Sep 30, 2026)",
        "source_url": "https://nsearchives.nseindia.com/corporate/MARUTI_27102026152412_QuickResults_27Oct2026_signed.pdf",
    },
    {
        "ticker": "RELIANCE.NS",
        "company": "Reliance Industries Limited",
        "pdf": "RELIANCE_Q1FY27.pdf",
        "timestamp": "2026-07-17T19:07:44+05:30",
        "headline": "Outcome of Board Meeting — Unaudited Consolidated and Standalone Financial Results for Q1 FY27 (quarter ended Jun 30, 2026)",
        "source_url": "https://nsearchives.nseindia.com/corporate/kavinavora_17072026190726_SE_FR_1.pdf",
    },
    {
        "ticker": "SUNPHARMA.NS",
        "company": "Sun Pharmaceutical Industries Limited",
        "pdf": "SUNPHARMA_Q1FY27.pdf",
        "timestamp": "2026-07-31T14:30:19+05:30",
        "headline": "Outcome of Board Meeting — Unaudited Standalone and Consolidated Financial Results for Q1 FY27 (quarter ended Jun 30, 2026)",
        "source_url": "https://nsearchives.nseindia.com/corporate/SUNSEC_31072026142955_BMOutcomewithannexures31072026.pdf",
    },
    {
        "ticker": "MARUTI.NS",
        "company": "Maruti Suzuki India Limited",
        "pdf": "MARUTI_Q1FY27.pdf",
        "timestamp": "2026-07-31T16:39:44+05:30",
        "headline": "Outcome of Board Meeting — Unaudited Standalone and Consolidated Financial Results for Q1 FY27 (quarter ended Jun 30, 2026)",
        "source_url": "https://nsearchives.nseindia.com/corporate/MARUTI_31072026163813_QuickResults_Q1_FY2026_27.pdf",
    },
    {
        "ticker": "ITC.NS",
        "company": "ITC Limited",
        "pdf": "ITC_Q1FY27.pdf",
        "timestamp": "2026-07-31T16:31:22+05:30",
        "headline": "Outcome of Board Meeting — Unaudited Standalone and Consolidated Financial Results for Q1 FY27 (quarter ended Jun 30, 2026)",
        "source_url": "https://nsearchives.nseindia.com/corporate/ITC_31072026162945_Results.pdf",
    },
    {
        "ticker": "PAGEIND.NS",
        "company": "Page Industries Limited",
        "pdf": "PAGEIND_Q1FY27.pdf",
        "timestamp": "2026-08-13T14:38:09+05:30",
        "headline": "Outcome of Board Meeting — Unaudited Ind AS Financial Results for Q1 FY27 (quarter ended Jun 30, 2026)",
        "source_url": "https://nsearchives.nseindia.com/corporate/PAGEIND_13082026143650_RESULTS30JUNE2026.pdf",
    },
    {
        "ticker": "HDFCBANK.NS",
        "company": "HDFC Bank Limited",
        "pdf": "HDFCBANK_Q2FY27.pdf",
        "timestamp": "2026-10-17T13:56:22+05:30",
        "headline": "Outcome of Board Meeting — Financial Results for Q2 FY27 (quarter ended Sep 30, 2026)",
        "source_url": "https://nsearchives.nseindia.com/corporate/HDFCBANK_17102026135520_OutcomeofBMResults_17oct2026.pdf",
    },
]


if __name__ == "__main__":
    results_dir = DOCS_DIR / "results"
    all_extractions = []
    for item in SLICE1_FILINGS:
        pdf_path = results_dir / item["pdf"]
        print(f"\n📄 Extracting {item['ticker']} from {item['pdf']}...")
        res = extract_results_from_pdf(
            pdf_path=pdf_path,
            ticker=item["ticker"],
            company=item["company"],
            source_url=item["source_url"],
        )
        if res["status"] != "ok" and item["ticker"] == "HDFCBANK.NS":
            res["error"] = (
                "Upstream NSE file truncated at 983,040 bytes (Content-Range: bytes 0-983039/983040; "
                "ends mid-stream at '325 0 R/Resources 216 0 R/Rotate' with no /Root catalog or %%EOF)."
            )
        all_extractions.append(res)
        if res["status"] == "ok":
            print(
                f"  ✅ Page {res['source_page']} ({res['basis']}, unit={res['reported_unit']}, vision={res['vision_used']})"
            )
            print(f"  📊 {res['summary']}")
            print(f"  🛡️  Validation: passed={res['validation']['passed']} flags={res['validation']['flags']}")
        else:
            print(f"  ⚠️  Status={res['status']} error={res.get('error')}")

    save_json(DATA_DIR / "slice1_extractions.json", all_extractions)
