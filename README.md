# FINN — Financial Investment Agent

**Product POV:** Filtering, not aggregating. A chief-of-staff mobile-first web application (`390px–430px` viewport) built around the **"Morning Briefing + Command Bar"** interaction model. Every screen answers *"so what?"* in one line using **primary sources only** (official NSE/BSE filings and earnings conference call transcripts). Zero news articles, zero broker notes, zero fabricated data.

---

## Live vs. Cached Components (Transparency Statement)

FINN separates **offline data ingestion & AI extraction** (Python pipeline) from **request-time serving** (Next.js App Router) so the web UI is fast, deterministic, and immune to upstream exchange WAF blocks during evaluation.

| Layer / Feature | Status in Repo | Upstream Primary Source | How It Works |
|---|---|---|---|
| **EOD Prices & Volume-Spike Alerts** (`data/prices/*.json`) | **Real data cached on disk** (refreshed `2026-10-27` via live `yfinance` `1.2.0` across all 18 NSE tickers) | Yahoo Finance (`*.NS`) | [`pipeline/fetch_prices.py`](pipeline/fetch_prices.py) pulls 90-day OHLCV bars, drops partial intraday bars before `16:00 IST`, computes the prior 20-session SMA (`shift(1).rolling(20).mean()`), and applies a **corporate-action guard (`vol_guard`)** that pauses volume alerts when a stock split, bonus, `<20` prior sessions, or `>20%` overnight price gap (e.g., demerger) falls inside the 20-day window. |
| **Results Filing Extraction — Slice 1** (`data/slice1_extractions.json`) | **Real primary extractions cached on disk** (PDFs gitignored, cached locally in `data/documents/results/*.pdf`, citations grounded in text evidence) | NSE Corporate Archives (`nsearchives.nseindia.com/corporate/*.pdf`) | [`pipeline/extract_results.py`](pipeline/extract_results.py) scores pages deterministically (Consolidated over Standalone), detects broken embedded OCR in scanned PDFs (`RELIANCE_Q1FY27.pdf` p. 9, `INFY_Q2FY27.pdf` p. 18, `MARUTI_Q2FY27.pdf` p. 6) and renders those pages to PNG via `pypdfium2`, extracts raw line items in native units (`crore`, `million`, `lakh`), normalises to `₹ crore` in Python, computes Schedule III Operating EBITDA (`"not_applicable"` for banks), records line-item derivations (Gross vs Net of Excise, PBT before/after exceptional), and validates `EBITDA < Revenue` and `PAT <= PBT`. |
| **Corporate Announcements Digest & Mgmt Change Enrichment** (`data/announcements/*.json`) | **100% of 30-day NSE filings ingested without caps** (180 unique non-XML announcements across 15 portfolio stocks; 63.3% classified via rules, 0 false results cards) | NSE Corporate Announcements API (`www.nseindia.com/api/corporate-announcements`) | BSE (`api.bseindia.com`) blocks automated requests with Akamai `403`. [`pipeline/fetch_announcements.py`](pipeline/fetch_announcements.py) uses `curl_cffi` (`impersonate="chrome"`) against NSE's JSON API, uses rule-first classification to save 114 LLM calls, attaches Slice 1 results strictly by URL and period (never by ticker alone), and downloads the actual PDF for `management_change` filings to extract incoming/outgoing executive backgrounds with page citations. |
| **Pull Mode — "Narrative vs. Numbers"** (`data/research/*.json`) | **8 companies pre-computed** (`INFY.NS`, `RELIANCE.NS`, `TCS.NS`, `ICICIBANK.NS`, `ETERNAL.NS`, `PIDILITIND.NS`, `BAJFINANCE.NS`, `ITC.NS`); **CLI runs live for any NSE ticker** | NSE Corporate Archives (`concall_transcript` + `results_filing` PDFs over last 4–5 quarters) | [`pipeline/generate_research.py`](pipeline/generate_research.py) uses smart page selection (first 5 pages prepared remarks + quantitative keyword-scored Q&A, and P&L statement pages) within a per-quarter token budget, dropping boilerplate pages, runs Gemini Flash, and enforces the **strict Citation Gate v3**: zero page tolerance, every number in claim appears inside the contiguous quote, and chronological priority (`guided_quarter < delivered_quarter`). Every verified claim writes source text to `evidence/{SYM}/`. |
| **Morning Briefing Assembly, Configurable Alerts & Window Selector** (`/`, `/api/digest`) | **Live at request time** (`force-dynamic`) | Reads `data/prices/*.json` and `data/announcements/*.json` | [`lib/data.ts`](lib/data.ts) (`getDigest()`) dynamically filters announcements by the selected lookback window (`24h`, `3d`, `7d`, `30d`), evaluates configurable alert settings (volume multiple N, price move ±X%, watched filing categories) across trading sessions in the window, and persists custom settings in `localStorage`. |

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
- [`COVERING_NOTE.md`](COVERING_NOTE.md) — Executive covering note (<600 words) summarizing what was built, key decisions, mistakes & lessons learned, and next steps.
- [`DECISIONS.md`](DECISIONS.md) — Complete 30-item architectural and data decisions log, mistakes table, and known limitations.
- [`build_history/SECRETS_SCAN.md`](build_history/SECRETS_SCAN.md) — Automated security scan verifying 0 secrets in git history and untracked `.env`.
- [`pipeline/extract_results.py`](pipeline/extract_results.py) — Slice 1 results PDF page scorer, `pypdfium2` vision fallback, unit normaliser (`crore`/`million`/`lakh` → `₹ crore`), Schedule III Operating EBITDA calculator, and accounting validator.
- [`pipeline/fetch_announcements.py`](pipeline/fetch_announcements.py) — NSE announcement fetcher (`curl_cffi`), materiality classifier, and `management_change` PDF enricher.
- [`pipeline/generate_research.py`](pipeline/generate_research.py) — Multi-quarter NSE transcript + results PDF fetcher and citation-verified "Narrative vs. Numbers" analyzer.
- [`pipeline/citation_gate.py`](pipeline/citation_gate.py) — Citation Gate v3 engine with 12 negative test cases.
- [`data/slice1_extractions.json`](data/slice1_extractions.json) — Full raw + normalised extraction output across the test filings with derivation formulas.
- [`data/llm_log.json`](data/llm_log.json) — Complete token and cost audit log for every Gemini API call.

---

## Known Limitations

1. **Priority Tiers (Code Implementation vs Architecture Hierarchy)**:
   - In `pipeline/fetch_announcements.py`, `dividend` and `fund_raise` are assigned to Priority 1 Material by deterministic rule (`classify_by_rules()` lines 291–298), and `capex` / order wins are assigned to Priority 1 Material by LLM prompt instruction (`CLASSIFICATION_PROMPT` line 115).
2. **Unenforceable `> ₹10 Cr` Regulatory Threshold**:
   - The design spec called for regulatory/tax orders `> ₹10 Cr` to be Priority 1 and `< ₹10 Cr` to be Priority 2. In practice, exchange headline subjects and one-line summaries rarely state the penalty quantum upfront, making the `> ₹10 Cr` criterion unenforceable without deep multi-page legal document parsing.
3. **Thin Summaries for Order Wins & Regulatory Penalties**:
   - Contract wins (L&T) and tax penalty notices (Maruti) receive generic 1-sentence summaries ("Company secured new business orders/contracts") because the pipeline only parses statutory annexures for management changes.
4. **30-Day Triage Volume (~50 material items)**:
   - A 30-day window generates ~50 material items across 15 stocks. This is comprehensive but too dense for a quick morning scan without company-level grouping or sector tabs.
5. **Historical Git Blobs (Scrubbed)**:
   - Historical PDF blobs in the git pack (~60.8 MiB) were scrubbed via `git filter-repo --path data/documents --invert-paths --force`, reducing git pack size to 553 KiB with 0 PDF objects remaining.
