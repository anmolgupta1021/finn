"""
Populate exact line-item `derivation` labels on all Slice 1 extractions
in `data/slice1_extractions.json`.
"""
from __future__ import annotations

import json
from config import DATA_DIR, save_json

DERIVATIONS = {
    "ICICIBANK.NS": {
        "basis_note": "Consolidated Financial Results (PDF p. 13, reported in ₹ crore; Banking Regulation Act Form A/B format).",
        "revenue_definition": "Bank Total Income = Interest Earned + Other Income = ₹88,161.18 Cr (Q1 FY27: ₹79,689.22 Cr; Q2 FY26: ₹76,146.59 Cr).",
        "ebitda_formula": "Not applicable (`not_applicable`) for banking companies (interest is an operating item). Operating Profit before Provisions & Contingencies = ₹24,009.97 Cr.",
        "pbt_basis": "Profit before tax (after provisions & contingencies of ₹818.22 Cr; no exceptional items) = ₹23,191.75 Cr.",
        "pat_basis": "Consolidated Net Profit for the period (Total Consolidated PAT) = ₹16,333.18 Cr.",
    },
    "INFY.NS": {
        "basis_note": "Statement of Consolidated Audited Financial Results under Ind AS (PDF p. 18 via vision, reported in ₹ crore).",
        "revenue_definition": "Revenue from Operations = ₹49,244 Cr (excludes Other Income of ₹969 Cr).",
        "ebitda_formula": "Operating Profit (Revenue ₹49,244 Cr − Total Expenses ₹39,029 Cr = ₹10,215 Cr) + Finance Costs (₹115 Cr) + Depreciation & Amortisation (₹1,359 Cr) = ₹11,689 Cr (23.74% margin).",
        "pbt_basis": "Profit Before Tax (before & after exceptional items; exceptional items = ₹0) = ₹11,063 Cr.",
        "pat_basis": "Total Consolidated Profit for the period = ₹7,838 Cr (Profit attributable to owners of the company = ₹7,823 Cr; Non-controlling interest = ₹15 Cr).",
    },
    "TCS.NS": {
        "basis_note": "Statement of Consolidated Interim Financial Results under Ind AS (PDF p. 8, reported in ₹ crore).",
        "revenue_definition": "Revenue from Operations = ₹73,188 Cr (excludes Other Income of ₹1,337 Cr).",
        "ebitda_formula": "Operating Profit (Revenue ₹73,188 Cr − Total Expenses ₹55,887 Cr = ₹17,301 Cr) + Finance Costs (₹252 Cr) + Depreciation & Amortisation (₹1,262 Cr) = ₹18,815 Cr (25.71% margin).",
        "pbt_basis": "Profit Before Tax (no exceptional items in Q2 FY27; Q2 FY26 had ₹616 Cr exceptional legal settlement provision) = ₹18,638 Cr.",
        "pat_basis": "Total Consolidated Profit for the period = ₹13,934 Cr (Profit attributable to shareholders of the company = ₹13,884 Cr; Non-controlling interest = ₹50 Cr).",
    },
    "RELIANCE.NS": {
        "basis_note": "Statement of Consolidated Unaudited Financial Results (PDF p. 9 via vision, reported in ₹ crore).",
        "revenue_definition": "Revenue from Operations (Net of GST/Excise) = ₹3,11,850 Cr.",
        "ebitda_formula": "Operating Profit (Revenue ₹3,11,850 Cr − Total Expenses ₹2,87,770 Cr = ₹24,080 Cr) + Finance Costs (₹8,337 Cr) + Depreciation, Depletion & Amortisation (₹15,100 Cr) = ₹47,517 Cr (15.24% margin).",
        "pbt_basis": "Profit Before Tax (after Share of Profit of Associates/JVs; no exceptional items in Q1 FY27) = ₹30,630 Cr.",
        "pat_basis": "Total Consolidated Profit for the period = ₹23,196 Cr (Profit attributable to Owners of the Company = ₹20,946 Cr; Non-controlling interest = ₹2,250 Cr).",
    },
    "SUNPHARMA.NS": {
        "basis_note": "Statement of Consolidated Unaudited Financial Results (PDF p. 10, reported in ₹ Million; normalised ÷10 to ₹ crore).",
        "revenue_definition": "Revenue from Operations = ₹1,52,998.8 Mn ÷ 10 = ₹15,299.88 Cr.",
        "ebitda_formula": "Operating Profit (Revenue ₹1,52,998.8 Mn − Total Expenses ₹1,17,206.0 Mn = ₹35,792.8 Mn) + Finance Costs (₹996.7 Mn) + Depreciation & Amortisation (₹7,387.2 Mn) = ₹44,176.7 Mn ÷ 10 = ₹4,417.67 Cr (28.87% margin).",
        "pbt_basis": "Profit Before Exceptional Items and Tax = ₹40,988.1 Mn ÷ 10 = ₹4,098.81 Cr (before exceptional items of ₹3,234.4 Mn).",
        "pat_basis": "Total Consolidated Profit for the period (after tax and exceptional items) = ₹28,947.9 Mn ÷ 10 = ₹2,894.79 Cr.",
    },
    "MARUTI.NS": {
        "basis_note": "Statement of Consolidated Unaudited Financial Results (PDF p. 4 via vision, reported in ₹ Million; normalised ÷10 to ₹ crore).",
        "revenue_definition": "Total Revenue from Operations (Net Sales + Operating Income) = ₹5,24,698 Mn ÷ 10 = ₹52,469.80 Cr.",
        "ebitda_formula": "Operating Profit (Revenue ₹5,24,698 Mn − Total Expenses ₹5,00,003 Mn = ₹24,695 Mn) + Finance Costs (₹635 Mn) + Depreciation & Amortisation (₹17,803 Mn) = ₹43,133 Mn ÷ 10 = ₹4,313.30 Cr (8.22% margin).",
        "pbt_basis": "Profit Before Tax (including Share of Profit of Associates; no exceptional items) = ₹44,412 Mn ÷ 10 = ₹4,441.20 Cr.",
        "pat_basis": "Total Consolidated Profit for the period = ₹34,469 Mn ÷ 10 = ₹3,446.90 Cr (100% attributable to owners of the company: ₹3,446.90 Cr).",
    },
    "ITC.NS": {
        "basis_note": "Statement of Consolidated Unaudited Financial Results (PDF p. 6, reported in ₹ crore; Note: PDF Column 2 is YoY 30.06.2025 and Column 3 is QoQ 31.03.2026).",
        "revenue_definition": "Revenue from Operations (Gross Revenue ₹29,523.30 Cr including Excise Duty; Net Revenue from Operations). Normalised in ₹ crore.",
        "ebitda_formula": "Operating Profit (Revenue ₹29,523.30 Cr − Total Expenses ₹24,809.95 Cr = ₹4,713.35 Cr) + Finance Costs (₹39.78 Cr) + Depreciation & Amortisation (₹427.73 Cr) = ₹5,180.86 Cr (17.55% margin).",
        "pbt_basis": "Profit Before Exceptional Items and Tax = ₹5,860.85 Cr.",
        "pat_basis": "Total Consolidated Profit for the period from Continuing Operations = ₹4,508.79 Cr (Profit attributable to owners of the parent = ₹4,394.13 Cr; Non-controlling interest = ₹114.66 Cr).",
    },
    "PAGEIND.NS": {
        "basis_note": "Standalone Unaudited Ind AS Financial Results (PDF p. 2, reported in ₹ Lakhs; normalised ÷100 to ₹ crore). Confirmed on PDF Page 3, Note 9: 'The Company has no subsidiary/ associate/ joint venture company(ies) as at June 30, 2026' — therefore Page Industries has no consolidated financial statement.",
        "revenue_definition": "Revenue from Operations (net of sales incentives per Note 4) = ₹1,42,044.53 Lakhs ÷ 100 = ₹1,420.45 Cr.",
        "ebitda_formula": "Operating Profit (Revenue ₹1,42,044.53L − Total Expenses ₹1,17,248.86L = ₹24,795.67L) + Finance Costs (₹1,243.33L) + Depreciation & Amortisation (₹2,861.33L) = ₹28,900.33 Lakhs ÷ 100 = ₹289.00 Cr (20.35% margin).",
        "pbt_basis": "Profit Before Tax (no exceptional items in Q1 FY27; FY26 full year had ₹3,500.42L New Labour Code exceptional item per Note 7) = ₹25,857.13 Lakhs ÷ 100 = ₹258.57 Cr.",
        "pat_basis": "Total Profit for the period (100% Standalone entity, no non-controlling interest) = ₹19,280.62 Lakhs ÷ 100 = ₹192.81 Cr.",
    },
}


def main() -> None:
    path = DATA_DIR / "slice1_extractions.json"
    items = json.loads(path.read_text())
    for item in items:
        t = item.get("ticker")
        if t in DERIVATIONS:
            item["derivation"] = DERIVATIONS[t]
        elif t == "HDFCBANK.NS":
            item["quarter"] = "Q2 FY27"
            item["source_url"] = "https://nsearchives.nseindia.com/corporate/HDFCBANK_17102026135520_OutcomeofBMResults_17oct2026.pdf"
            item["error"] = (
                "Upstream NSE file truncated at 983,040 bytes (Content-Range: bytes 0-983039/983040; "
                "ends mid-stream at '325 0 R/Resources 216 0 R/Rotate' with no /Root catalog or %%EOF)."
            )
            item["highlights"] = "Filing couldn't be read, open original"
    save_json(path, items)
    print(f"Updated {len(items)} entries in slice1_extractions.json with derivations & HDFCBANK fallback.")


if __name__ == "__main__":
    main()
