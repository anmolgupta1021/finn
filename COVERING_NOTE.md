# FINN — Covering Note

## 1. What Was Built
FINN is an investment research agent for Indian equities at 390px.
**Interaction Point of View**: Filtering, not aggregating — a mobile-first "Morning Briefing + Command Bar" answering "so what?" in one line grounded in primary filings, not news or memory.
1. **Daily Briefing (Push)**: Morning triage for 15 portfolio stocks. Evaluates EOD price/volume alerts (24h, 3d, 7d, 30d), ingests 100% of NSE filings, extracts results with Schedule III derived EBITDA, and summarizes management changes with bios where provided.
2. **Ad-hoc Research (Pull)**: Multi-quarter analysis across 8 pre-computed companies (4 ad-hoc: Bajaj Finance, Eternal, ITC, Pidilite; 4 portfolio: Infosys, Reliance, TCS, ICICI Bank). Enforces **Citation Gate v3**: zero page tolerance, chronological priority, and a number-in-quote rule (every digit in a claim must appear inside the quote).

## 2. Key Decisions
- **Fail-Closed Primary Sources**: Corrupted filings (`HDFCBANK_Q2FY27.pdf`) render honest error cards rather than secondary estimates.
- **Rule-First Pipeline**: 63% of routine filings triaged via rules, saving 114 LLM calls.
- **Derived EBITDA Integrity**: Ind-AS statements rarely report EBITDA. FINN derives Operating EBITDA (Operating Profit + D&A), labeled derived; bank EBITDA marked not applicable.
- **Configurable Alerts**: Thresholds configurable in a settings panel persisted in `localStorage`.

## 3. Deliberately Left Out
- **Six Pull Lenses, Chat & Annual Reports**: Cut because of the time-box, to build one lens with verified citations.
- **BSE Ingestion**: BSE API was tested on 2026-10-27 and returned HTTP 403 (Akamai WAF); NSE alone covered the portfolio.
- **Deployed Live Research**: Disabled on Vercel because NSE blocks cloud server IPs; cold-ticker research runs locally via `pipeline/generate_research.py`.

## 4. Cost Per Query (`data/llm_log.json`)
- **Uncached**: ~19k–48k input tokens; output split into 453–2,179 candidate and 9,668–16,819 thinking tokens (total: 10,121–18,422). Cost: $0.0309–$0.0577 per company on `gemini-3.8-flash` ($0.0047 on `gemini-3.5-flash-lite`).
- **Cached**: 0 tokens, $0.0000 cost (local content-hash hit).

## 5. Mistakes Made & How Caught
- **Caught by Audits**: Synthetic demo data purged in commit "Snapshot before correction". Fabricated Slice 1 chat table caught by checking numbers against `data/slice1_extractions.json` and PDFs. Results cards attaching to intimations caught in feed audits. Naive text truncation that "dropped about 60% of pages, including all results filings" caught by Pidilite recall audit.
- **Caught by User Review**: Discrepancy claiming portfolio included `SBIN`/`HCLTECH`, and the hardcoded `(Net of GST)` string on L&T/Maruti where not printed.
- **Verification Integrity**: Because agent self-verification proved unreliable, verification was redone against the PDFs and extraction JSON. Full details in [`DECISIONS.md`](DECISIONS.md).

## 6. Known Limitations
- **Quarters Actually Produced**: INFY (4), BAJFINANCE (4), ICICIBANK (4), PIDILITIND (4), RELIANCE (3), TCS (3), ETERNAL (2), ITC (1). Earlier reports counted all 5–6 quarters of fetched source documents in the manifest, not narrative output.
- **Primary Sources**: Annual reports unused; grounded strictly in earnings transcripts and results filings.
- **Excise Duty**: Reliance and ITC revenues are reported gross of excise duty (itemized in expenses).
- **Auto-checked Badge**: Denotes automated mathematical sanity checks (EBITDA < revenue, PAT $\le$ PBT), not human review.
- **Verification Statement**: Hand-checked by me against: [FILL IN]

## 7. Next Steps
- **Omitted Lenses**: Implement balance sheet, cash quality (operating cash flow vs PAT), and trajectory lenses with primary table citations.
- **Annual-Report Indexing**: Extract and index multi-hundred-page annual reports into chunked, citation-gated storage.
- **Live Research Worker / Proxy**: Deploy a residential proxy or background worker queue to bypass cloud IP blocks on exchange servers, enabling on-demand live generation directly from the web app.
