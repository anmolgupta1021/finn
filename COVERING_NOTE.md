# FINN — Covering Note

## 1. What Was Built
FINN is an investment research agent for Indian public equities, designed mobile-first at 390px.
1. **Daily Briefing (Push)**: Morning triage for 15 portfolio companies across key sectors. Evaluates end-of-day price and volume thresholds (customizable $N\times$ volume spike, $\pm X\%$ price move), ingests corporate filings from NSE archives, extracts quarterly P&L results with Schedule III derived EBITDA formulas, and summarizes management changes with executive biographies where the filing includes one.
2. **Ad-hoc Research (Pull)**: Deep-dive multi-quarter analysis across 8 pre-computed research companies (4 ad-hoc: Bajaj Finance, Eternal, ITC, Pidilite; 4 portfolio: Infosys, Reliance, TCS, ICICI Bank) using primary filings. Enforces **Citation Gate v3**: zero page tolerance, chronological priority, and a number-in-quote rule (every digit in a claim must appear inside the contiguous verbatim quote).

## 2. Key Decisions
- **Fail-Closed Primary Sources**: No broker notes, street consensus, or news memory. Corrupted filings (e.g. truncated `HDFCBANK_Q2FY27.pdf`) render honest fallback cards rather than secondary estimates.
- **Rule-First Pipeline**: 63% of routine filings are triaged via deterministic rules, saving 114 LLM calls.
- **Derived EBITDA Integrity**: Ind-AS statements rarely report EBITDA. FINN derives Operating EBITDA (Operating Profit + D&A), labels it as derived, and marks bank EBITDA as not applicable.
- **Client-Configurable Alerts**: Users configure thresholds via a settings panel persisted in `localStorage`.

## 3. Deliberately Left Out
- **Six Pull Lenses**: Business snapshot, financial snapshot, trajectory, balance sheet, cash quality, and bull vs bear were omitted to focus engineering on verifiable primary citations.
- **Annual Reports & Freeform Chat**: Omitted ungrounded conversational chat and multi-hundred-page annual reports to prevent hallucination.
- **BSE API & Deployed Live Research**: BSE API was dropped due to Akamai WAF blocks. Live generation is disabled on the deployed Vercel app because NSE blocks cloud server IPs; cold-ticker research is run via the local CLI pipeline (`pipeline/generate_research.py`).

## 4. Cost Per Query (`data/llm_log.json`)
- **Uncached Query**: ~19k–48k input tokens; output tokens split into 453–2,179 candidate tokens and 9,668–16,819 thinking tokens (total output: 10,121–18,422 tokens). Cost ranges from $0.0309 to $0.0577 per company on `gemini-3.8-flash` ($0.0047 on `gemini-3.5-flash-lite`).
- **Cached Query**: 0 input tokens, 0 output tokens, $0.0000 cost (local content-hash cache hit).

## 5. Mistakes Made & How Caught
Early prototypes encountered ticker verification failures, model-authored synthetic fixtures, a fabricated Slice 1 chat table, false results attachments by ticker alone, naive text truncation that "dropped about 60% of pages, including all results filings", and hardcoded derivation strings. Each mistake was caught via integrity audits, feed reviews, and primary-source cross-checks, and resolved with permanent automated gates.
*Full mistake details, root causes, and fixes are cataloged in [`DECISIONS.md`](DECISIONS.md).*

## 6. Known Limitations
- **Quarters Available**: INFY (6), ETERNAL (6), BAJFINANCE (5), ICICIBANK (5), ITC (5), PIDILITIND (5), RELIANCE (5), TCS (5).
- **Primary Sources**: Annual reports are unused; analysis is grounded strictly in earnings transcripts and results filings.
- **Excise Duty**: Reliance and ITC revenues are reported gross of excise duty (excise duty itemized in expenses).
- **Auto-checked Badge**: Indicates automated mathematical and accounting sanity checks (EBITDA < revenue, PAT ≤ PBT), not human audit review.
- **Verification Statement**: Hand-checked by me against: [FILL IN]

## 7. Next Steps
- Real-time exchange webhooks and cash flow statement extraction (operating cash flow vs PAT).
