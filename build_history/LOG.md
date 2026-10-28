# FINN — Build History Log

Chronological summary of development, hardening, and verification phases:

## Phase 1: Prototype Scaffolding & Initial Integrity Reset (2026-10-27)
- **Scaffold**: Next.js App Router, Tailwind CSS, shadcn/ui components, and Python offline data pipelines.
- **Correction Event (`019b139`)**: Discovered subagent hallucinated ticker validation and generated synthetic demo files (`digest.json`, sample research).
- **Integrity Reset**: Immediately purged all invented data files. Switched to fail-closed empty states. Validated all tickers with real `yfinance` queries. Replaced non-quoting `TATAMOTORS.NS` with `TMPV.NS` and old `ZOMATO.NS` with `ETERNAL.NS`.

## Phase 2: Slice 1 Financial Extraction & Pipeline Hardening (2026-10-27)
- **BSE vs NSE**: Discovered BSE API blocked by Akamai WAF. Switched to NSE corporate announcements API via `curl_cffi` session impersonation.
- **Statement Extraction (`pipeline/extract_results.py`)**: Built deterministic page scoring and `pypdfium2` vision rendering (scale=2.0) for broken OCR tables.
- **Schedule III Derived EBITDA**: Built automated line-item derivation for Operating Profit + D&A. Added `status: "not_applicable"` for banks with Operating Profit before provisions.
- **Fail-Closed PDF Handling**: Handled upstream corrupted `HDFCBANK_Q2FY27.pdf` with explicit warning card instead of inventing numbers.

## Phase 3: Pull-Side Multi-Quarter Research & Citation Gate (2026-10-27 – 2026-10-28)
- **Citation Gate v1 & v2**: Required `(doc_id, page)` validation and token overlap on extracted transcript pages.
- **Citation Gate v3 Hardening**:
  - Removed `±1` page tolerance (strict exact-page requirement).
  - Number-in-quote rule: every digit in claim text must exist verbatim inside the contiguous quote.
  - Chronology guard: `guided_doc_quarter < delivered_doc_quarter` must hold strictly, preventing hindsight.
  - Validated against 12 negative test cases with 12/12 rejected.

## Phase 4: Push Feed Hardening & Mobile Optimization (2026-10-28)
- **URL & Period Attachment**: Fixed results card attachment bug to match strictly on normalized PDF URL and quarter period.
- **Uncapped Ingestion**: Ingested 180 announcements across all 15 portfolio tickers without caps. Rule engine classified 114 filings, saving 114 LLM calls.
- **Alerts Feed De-duplication**: Omitted priority 1 announcements from the top ALERTS banner to prevent duplicating the WHAT MATTERS section.
- **Configurable Settings Panel**: Persisted volume threshold ($N$), price move ($\pm X\%$), and watched filing categories in `localStorage`.
- **Timezone Integrity**: Fixed UTC server render on Vercel by formatting in `Asia/Kolkata` with `suppressHydrationWarning`.
- **Badge Transparency**: Renamed "Checked" badge to "Auto-checked" with explanatory tooltip and footnote.
