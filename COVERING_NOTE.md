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

## 3. Mistakes Made & Lessons Learned
- **Synthetic Demo Data**: An early prototype generated synthetic demo figures before the extraction pipeline was built. We halted development, purged all invented files in commit `019b139`, and instituted empty states.
- **Status Report Discrepancy**: A progress report claimed the core portfolio had changed to include `SBIN` and `HCLTECH`. The repository never had those stocks. We verified `data/portfolio.json` directly against git.
- **Fixed String Hardcoding**: The derivation string hardcoded `(Net of GST)` across all companies. We eliminated the string in favor of exact printed line labels.

## 4. Limitations
- **Priority Tier Inconsistency**: The pipeline rule engine and prompt assign `dividend`, `fund_raise`, and `capex` to Priority 1 Material rather than Priority 2 Notable.
- **Thin Non-Management Summaries**: Order wins (L&T) and tax penalty notices (Maruti) receive generic one-sentence summaries because the pipeline only parses statutory annexures for management changes.
- **30-Day Triage Density**: A 30-day window generates ~50 material items across 15 stocks, which is too dense without company-level grouping.
- **Historical Git Blobs**: The repository working tree is clean, but old commits retain ~60 MiB of PDF blobs in git pack history.

## 5. Next Steps
- **Exchange Webhooks & PDF Queue**: Connect directly to BSE/NSE real-time feeds with an async worker queue.
- **Balance Sheet & Cash Quality**: Extend the multi-quarter extraction engine to cash flow statements (operating cash flow vs PAT) and working capital ratios.
- **Multi-Channel Delivery**: Push morning digests via Telegram bot or WhatsApp Business API.
