# FINN — Covering Note

## 1. What Was Built
FINN is an institutional-grade investment research agent for Indian public equities, designed mobile-first at 390px. It delivers:
1. **Daily Briefing (Push)**: A morning triage dashboard for 15 portfolio companies across key sectors. Evaluates end-of-day price and volume thresholds (customizable $N\times$ volume spike, $\pm X\%$ price move), ingests corporate filings from NSE archives, extracts quarterly P&L results with Schedule III derived EBITDA formulas, and summarizes management changes with executive biographies.
2. **Ad-hoc Research (Pull)**: Deep-dive multi-quarter analysis on 4 non-overlapping companies (Bajaj Finance, Eternal, ITC, Pidilite) using only primary filings. Enforces **Citation Gate v3**: zero page tolerance, strict chronological precedence, and a number-in-quote rule (every digit in a claim must appear inside the cited verbatim quote).

## 2. Key Decisions
- **Fail-Closed Primary Sources**: No broker notes, street consensus, or news sentiment. Corrupted filings (e.g. truncated `HDFCBANK_Q2FY27.pdf`) render honest error cards rather than falling back to secondary data.
- **Rule-First Pipeline**: 63% of routine filings (share certificate losses, newspaper notices, compliance reports) are triaged via deterministic rules, saving 114 LLM calls.
- **Derived EBITDA Integrity**: Ind-AS statements rarely report EBITDA. FINN derives Operating EBITDA (Operating Profit + D&A), labels it as derived, records gross vs net excise duty (Reliance, ITC), and marks bank EBITDA as not applicable.
- **Client-Configurable Alerts**: Users configure thresholds via a settings panel persisted in `localStorage`.

## 3. Mistakes Made & How Caught
- **Synthetic Demo Data**: An early prototype generated synthetic demo figures before the extraction pipeline was built. Caught by codebase audit; purged in commit "Snapshot before correction".
- **Fabricated Slice 1 Chat Table**: An earlier chat report presented a hallucinated "hand-verified" table. Caught when the audit cross-checked the chat table against `data/slice1_extractions.json` and the PDFs; voided immediately.
- **Results Attachment by Ticker**: Results cards originally attached by ticker alone, causing cards to attach to prior intimations and UDIN notices. Caught during feed audits; fixed by matching strictly on PDF URL and period.
- **Truncated Pull Input (`corpus[:180000]`)**: A naive 180k-character slice dropped later quarterly transcripts. Caught during the Pidilite recall audit (only 47.7k input tokens sent for 169 pages); replaced with budgeted page scoring.
- **Status Report Discrepancy**: A progress report claimed the core portfolio had changed to include `SBIN` and `HCLTECH`. Caught by checking the live portfolio strip; verified against git.
- **Fixed String Hardcoding**: The derivation string hardcoded `(Net of GST)` across all companies. Caught during user review on L&T/Maruti; replaced with exact printed row labels.

## 4. Limitations
- **Priority Tier Implementation**: `dividend` and `fund_raise` are assigned to Priority 1 Material by rule, and `capex`/order wins are assigned to Priority 1 by the LLM prompt.
- **Unenforceable Regulatory Threshold**: The spec called for regulatory orders `> ₹10 Cr` to be P1 and `< ₹10 Cr` to be P2. In practice, exchange headlines rarely state penalty amounts, making this criterion unenforceable without deep legal parsing.
- **Thin Non-Management Summaries**: Order wins (L&T) and tax penalty notices (Maruti) receive generic one-sentence summaries because the pipeline only parses statutory annexures for management changes.
- **30-Day Triage Density**: A 30-day window generates ~50 material items across 15 stocks, which is too dense without company-level grouping.

## 5. Next Steps
- **Exchange Webhooks & PDF Queue**: Connect directly to BSE/NSE real-time feeds with an async worker queue.
- **Balance Sheet & Cash Quality**: Extend the multi-quarter extraction engine to cash flow statements (operating cash flow vs PAT) and working capital ratios.
- **Multi-Channel Delivery**: Push morning digests via Telegram bot or WhatsApp Business API.
