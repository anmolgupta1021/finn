# FINN — Covering Note

## 1. What Was Built
**Interaction Point of View**: Filtering, not aggregating — mobile-first (390px) "Morning Briefing + Command Bar" answering "so what?" in one line grounded in primary filings, not news or memory.
1. **Daily Briefing (Push)**: Morning triage across 15 portfolio stocks. Evaluates EOD alerts (24h, 3d, 7d, 30d), all announcements NSE's API returned for the window (completeness checked on HDFC Bank: 19/19), extracts results with Schedule III derived EBITDA, and summarizes management changes with bios where provided.
2. **Ad-hoc Research (Pull)**: Multi-quarter analysis across 8 pre-computed companies (4 ad-hoc, 4 portfolio). Enforces **Citation Gate v3**: zero page tolerance, chronological priority, and number-in-quote rule (every digit in a claim must appear inside the quote).

## 2. Key Decisions
- **Fail-Closed Sources**: Corrupted filings (`HDFCBANK_Q2FY27.pdf`) render honest error cards rather than secondary estimates.
- **Rule-First Pipeline**: 63% of routine filings triaged via rules, saving 114 LLM calls.
- **Derived EBITDA Integrity**: Ind-AS rarely reports EBITDA; FINN derives Operating EBITDA (Operating Profit + D&A) labeled derived (bank EBITDA marked not applicable).
- **Configurable Alerts**: Thresholds configurable in a settings panel persisted in `localStorage`.

## 3. Deliberately Left Out
- **Six Pull Lenses, Chat & Annual Reports**: Cut due to time-box, prioritizing one lens with verified citations.
- **BSE Ingestion**: Tested 2026-10-27; returned HTTP 403 (DECISIONS.md:42, pipeline/fetch_announcements.py:5, build_history/transcript.jsonl:286). NSE covered the portfolio.
- **Deployed Live Research**: Disabled on Vercel as NSE blocks cloud IPs; runs locally via `pipeline/generate_research.py`.

## 4. Cost Per Query (`data/llm_log.json`)
- **Uncached**: ~19k–48k input tokens; output split into 453–2,179 candidate and 9,668–16,819 thinking tokens (total: 10,121–18,422). Cost: $0.0309–$0.0577/co on `gemini-3.8-flash` ($0.0047 on `gemini-3.5-flash-lite`).
- **Cached**: 0 tokens, $0.0000 (local content-hash hit).

## 5. Mistakes Made & How Caught
- **Caught by Audits**: Synthetic demo data purged in commit "Snapshot before correction". Fabricated Slice 1 chat table caught against `data/slice1_extractions.json` and PDFs. Results cards attaching to intimations caught in feed audits. Truncation dropping ~60% of pages caught in Pidilite recall audit.
- **Caught by User Review**: An agent status report claimed the portfolio included `SBIN`/`HCLTECH`, and hardcoded `(Net of GST)` on L&T/Maruti where not printed.
- **Subagent Ticker Failure**: A subagent with no network access claimed tickers valid from web search, and the first real yfinance run caught TATAMOTORS.NS and ZOMATO.NS (now TMPV.NS and ETERNAL.NS).
- **Verification Integrity**: Because agent self-verification proved unreliable, verification was redone against PDFs and extraction JSON (details in [`DECISIONS.md`](DECISIONS.md)).

## 6. Known Limitations
- **Priority Tiers**: Dividend/fund_raise P1 by rule, capex/order wins P1 by LLM prompt (differs from design); >₹10 Cr criterion unenforceable on unquantified headlines.
- **Thin Summaries**: Generic 1-sentence summaries for order wins and regulatory penalties.
- **30-Day Density**: ~50 material items appear in 30-day view.
- **Quarters Produced**: INFY (4), BAJFINANCE (4), ICICIBANK (4), PIDILITIND (4), RELIANCE (3), TCS (3), ETERNAL (2), ITC (1) (earlier reports counted manifest docs, not narrative output).
- **Unused Sources**: Annual reports unused; relies on transcripts and results filings.
- **Excise Duty**: Reliance and ITC revenue gross of excise (itemized in expenses).
- **Auto-checked Badge**: Automated mathematical checks (EBITDA < revenue, PAT $\le$ PBT), not human review.
- **Verification Statement**: Hand-checked by me against: [FILL IN]

## 7. Next Steps
- **Omitted Lenses**: Add balance sheet, cash quality (OCF vs PAT), and trajectory lenses with primary table citations.
- **Annual-Report Indexing**: Index multi-hundred-page annual reports into chunked, citation-gated storage.
- **Live Research Worker / Proxy**: Deploy a residential proxy or worker queue bypassing exchange cloud IP blocks for live web app research.
