# FINN — Financial Investment Agent

**Product POV:** Filtering, not aggregating. A chief-of-staff mobile-first web application (`390px–430px` viewport) built around the **"Morning Briefing + Command Bar"** interaction model. Every screen answers *"so what?"* in one line using **primary sources only** (official NSE/BSE filings and earnings conference call transcripts). Zero news articles, zero broker notes, zero fabricated data.

---

## Live vs. Cached Components (Transparency Statement)

FINN separates **offline data ingestion & AI extraction** (Python pipeline) from **request-time serving** (Next.js App Router) so the web UI is fast, deterministic, and immune to upstream exchange WAF blocks during evaluation.

| Layer / Feature | Status in Repo | Upstream Primary Source | How It Works |
|---|---|---|---|
| **EOD Prices & Volume-Spike Alerts** (`data/prices/*.json`) | **Real data cached on disk** (refreshed `2026-10-27` via live `yfinance` `1.2.0` across all 18 NSE tickers) | Yahoo Finance (`*.NS`) | [`pipeline/fetch_prices.py`](pipeline/fetch_prices.py) pulls 90-day OHLCV bars, drops partial intraday bars before `16:00 IST`, computes the prior 20-session SMA (`shift(1).rolling(20).mean()`), and applies a **corporate-action guard (`vol_guard`)** that pauses volume alerts when a stock split, bonus, `<20` prior sessions, or `>20%` overnight price gap (e.g., demerger) falls inside the 20-day window. |
| **Results Filing Extraction — Slice 1** (`data/documents/results/*.pdf` → `data/slice1_extractions.json`) | **Real NSE PDFs cached on disk** + extracted via live `gemini-3.5-flash-lite` calls | NSE Corporate Archives (`nsearchives.nseindia.com/corporate/*.pdf`) | [`pipeline/extract_results.py`](pipeline/extract_results.py) scores pages deterministically (Consolidated over Standalone), detects broken embedded OCR in scanned PDFs (`RELIANCE_Q1FY27.pdf` p. 9, `INFY_Q2FY27.pdf` p. 18, `MARUTI_Q1FY27.pdf` p. 4) and renders those pages to PNG via `pypdfium2`, extracts raw line items in native units (`crore`, `million`, `lakh`), normalises to `₹ crore` in Python, computes Schedule III Operating EBITDA (`"not_applicable"` for banks), and validates `EBITDA < Revenue` and `PAT <= PBT`. |
| **Corporate Announcements Digest & Mgmt Change Enrichment** (`data/announcements/*.json`) | **Real NSE filings cached on disk** (92 announcements across 15 portfolio stocks) | NSE Corporate Announcements API (`www.nseindia.com/api/corporate-announcements`) | BSE (`api.bseindia.com`) blocks automated requests with Akamai `403`. [`pipeline/fetch_announcements.py`](pipeline/fetch_announcements.py) uses `curl_cffi` (`impersonate="chrome"`) against NSE's JSON API, classifies materiality (`1` Material, `2` Notable, `3` Routine/Noise) via `gemini-3.5-flash-lite`, and downloads the actual PDF for `management_change` filings (`data/documents/filings/*.pdf`) to extract incoming/outgoing executive backgrounds with page citations. |
| **Pull Mode — "Narrative vs. Numbers"** (`data/research/*.json`) | **Real NSE transcripts + results PDFs cached on disk** for `INFY.NS`, `RELIANCE.NS`, `TCS.NS`, `ICICIBANK.NS`, `ETERNAL.NS`; **CLI runs live for any NSE ticker** | NSE Corporate Archives (`concall_transcript` + `results_filing` PDFs over last 4–5 quarters) | [`pipeline/generate_research.py`](pipeline/generate_research.py) downloads the last 4–5 quarterly earnings call transcripts and financial results PDFs from NSE, extracts text page-by-page (`[DOC_X \| Page N]`), runs `gemini-3.6-flash`, and enforces a **strict Python citation gate**: any `guided` or `delivered` claim whose `(doc_id, page)` was not actually fetched and read is rejected. |
| **Morning Briefing Assembly & Window Selector** (`/`, `/api/digest?hours=...`) | **Live at request time** (`force-dynamic`) | Reads `data/prices/*.json` and `data/announcements/*.json` | [`lib/data.ts`](lib/data.ts) (`getDigest()`) dynamically filters announcements by the selected lookback window (`24h` default, `14d`, `30d`, `120d`), evaluates price/volume alert thresholds from `data/portfolio.json`, and renders honest empty states whenever a window has zero filings. |

---

## Verified Gemini Model Routing (Checked `2026-10-27`)

Model names were verified against `GET https://generativelanguage.googleapis.com/v1beta/models` and rate-limit documentation at `https://ai.google.dev/gemini-api/docs/rate-limits` (see [`DECISIONS.md`](DECISIONS.md) `#15`):
- **Bulk classification, summaries, and single-page table/filing extraction**: `gemini-3.5-flash-lite` (fallback `gemini-3.1-flash-lite`) — fast, multimodal PNG support, zero thinking-token overhead.
- **Multi-quarter "Narrative vs. Numbers" synthesis across 8–10 PDFs (~45k–65k input tokens)**: `gemini-3.6-flash` (fallback `gemini-3-flash-preview` / `gemini-3.5-flash-lite`).
- Every LLM call is content-hash cached in `data/.llm_cache/` and logged with exact token counts and cost in [`data/llm_log.json`](data/llm_log.json).

---

## Running Locally

### 1. Web Application (Next.js 15)
```bash
npm install
npm run build
npm start        # Serves production build on http://localhost:3000
# or: npm run dev
```

### 2. Offline Data & AI Pipeline (Python 3.9+)
Create `finn/.env` with `GEMINI_API_KEY=<your_key>` (confirmed gitignored in `.gitignore`).

```bash
pip install -r pipeline/requirements.txt

# 1. Verify all 18 portfolio + ad-hoc tickers against live Yahoo Finance
python3 pipeline/verify_tickers.py

# 2. Fetch 90-day EOD prices + compute 20-day volume ratios with corporate-action guard
python3 pipeline/fetch_prices.py

# 3. Run Slice 1 results PDF extractor (with pypdfium2 vision fallback & validation)
python3 pipeline/extract_results.py

# 4. Fetch, classify & enrich NSE corporate announcements across the 15 portfolio stocks
python3 pipeline/fetch_announcements.py

# 5. Generate "Narrative vs. Numbers" primary-source research for any NSE ticker(s)
python3 pipeline/generate_research.py INFY.NS RELIANCE.NS TCS.NS ICICIBANK.NS ETERNAL.NS
# Or run on any other NSE symbol on demand:
python3 pipeline/generate_research.py TITAN.NS
```

---

## Key Files
- [`DECISIONS.md`](DECISIONS.md) — Architectural, data, and model decisions log (including the transparent correction log from commit `019b139`).
- [`pipeline/extract_results.py`](pipeline/extract_results.py) — Slice 1 results PDF page scorer, `pypdfium2` vision fallback, unit normaliser (`crore`/`million`/`lakh` → `₹ crore`), Schedule III Operating EBITDA calculator, and accounting validator.
- [`pipeline/fetch_announcements.py`](pipeline/fetch_announcements.py) — NSE announcement fetcher (`curl_cffi`), materiality classifier, and `management_change` PDF enricher.
- [`pipeline/generate_research.py`](pipeline/generate_research.py) — Multi-quarter NSE transcript + results PDF fetcher and citation-verified "Narrative vs. Numbers" analyzer.
- [`data/slice1_extractions.json`](data/slice1_extractions.json) — Full raw + normalised extraction output across the 9 test filings.
- [`data/llm_log.json`](data/llm_log.json) — Complete token and cost audit log for every Gemini API call.
