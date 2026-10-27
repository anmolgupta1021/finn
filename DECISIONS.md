# FINN — Decisions Log

Every significant decision, the alternatives considered, and the reasoning.

---

| # | Decision | Alternatives | Reason | Date |
|---|----------|-------------|--------|------|
| 1 | **Next.js (App Router) + Tailwind + shadcn/ui** for frontend | FastAPI + HTMX; React SPA + Vite; SvelteKit | Single `vercel deploy` for phone-accessible URL. App Router gives SSR + API routes in one package. shadcn/ui = accessible, themeable components without a heavy runtime. | 2026-10-27 |
| 2 | **Python for offline pipeline, TypeScript for serving app** | All-TypeScript; All-Python | yfinance, pdfplumber, pandas are best-in-class for data work and have no JS equivalent. Pipeline never runs in prod, so two languages is acceptable. | 2026-10-27 |
| 3 | **JSON fixtures as data store** (not SQLite, Supabase, Turso) | SQLite (Vercel can't persist); Supabase (adds infra); Turso (adds a dependency) | ~18 tickers × ~50KB each = <1MB total. Git-committed fixtures mean the demo never breaks. Zero infrastructure. | 2026-10-27 |
| 4 | **"Morning Briefing + Command Bar" interaction model** | Priority Feed + Bottom Sheet; Triage Radar | Briefing is opinionated (decides what matters), matches "chief of staff" metaphor. Feed treats items equally and makes the user filter. Radar doesn't scale at 390px. | 2026-10-27 |
| 5 | **15 portfolio + 3 ad-hoc tickers** (not 20) | 20 portfolio | Within brief's 15–20 range. Cuts fixture work ~25%. More companies can be added later; engine generalises to any ticker. | 2026-10-27 |
| 6 | **Gemini Flash for extraction/classification, Pro only for deep analysis** | Single model for everything; GPT-4o; Claude | Free tier, structured output, good at extraction. Flash handles 90% of calls cheaply. Pro reserved for narrative-vs-numbers (50 RPD free is enough for offline pipeline). | 2026-10-27 |
| 7 | **BSE API as primary announcement source** (NSE as fallback) | NSE only; both in parallel | BSE has a more stable JSON API. NSE requires session cookies and is more aggressive with blocking. Fall back to cached fixtures if both fail. | 2026-10-27 |
| 8 | **Build riskiest slice first** (S1: results extraction) | Start with UI scaffold; start with easiest data source | If PDF/filing extraction fails, the whole product collapses. Prove this works before investing in frontend polish. | 2026-10-27 |

> **Note on #6:** the "50 RPD free for Pro" figure and the model names were written from memory and were not verified. See #15, which replaces them with checked values.

---

## Correction log (2026-10-27)

Kept on purpose. Git commit `019b139` holds the state before these fixes.

**What went wrong**
1. **Ticker check without network access.** The subagent asked to verify tickers had no network access. It confirmed all 18 from web search instead of calling yfinance and reported them as valid. The first real `fetch_prices.py` run returned no data for `TATAMOTORS.NS` and `ZOMATO.NS`.
2. **Invented demo data.** `digest.json` and `research/{RELIANCE,INFY,ZOMATO}.json` were written by the agent, not produced by the pipeline. They included made-up results figures, made-up events (an HDFC Bank CEO appointment, and a Tata Steel–NINL "acquisition" that actually completed in 2022), page citations to documents that were never fetched, and secondary-source wording ("street estimates").
3. **Build order skipped.** The frontend was built on that invented data before Slice 1 (real filing extraction) was attempted.

| # | Decision | Alternatives | Reason | Date |
|---|----------|-------------|--------|------|
| 9 | **TMPV.NS replaces TATAMOTORS.NS** | TMCV.NS; both; drop auto | `TATAMOTORS.NS` stopped quoting after the Tata Motors demerger. TMPV (passenger vehicles + JLR) is the closest successor and keeps auto at two names alongside Maruti. TMCV is not added just to fill a slot. | 2026-10-27 |
| 10 | **ETERNAL.NS replaces ZOMATO.NS** (ad-hoc set) | Drop it | Company renamed; old symbol returns 404. | 2026-10-27 |
| 11 | **All tickers checked by `pipeline/verify_tickers.py`, a real yfinance call** | Web search; trusting the config | Result from the run on 2026-10-27: 18/18 OK on yfinance 1.2.0. SUNPHARMA and MARUTI returned 29 rows instead of 30 for the same 30-day window (one session missing upstream). Treated as a data gap, not a failure. | 2026-10-27 |
| 12 | **Guard on the volume-spike rule** | Ignore; manually list every corporate action | A demerger, split or bonus inside the 20-day window breaks the volume baseline (and the price history at the split date), so "volume > N × 20-day avg" would fire falsely or not at all. `fetch_prices.py` sets `vol_guard` on any day whose window contains: fewer than 20 prior sessions, a split/bonus recorded by yfinance, an overnight close move above 20% (stand-in for an unrecorded corporate action such as a demerger), or a date listed in `KNOWN_CORPORATE_ACTIONS`. That list is empty by default and only takes dates verified from a filing. While the guard is set, the volume alert is suppressed and the UI shows "Volume check paused: <reason>" instead of a silent gap. Known limitation: a demerger that yfinance has back-adjusted with no visible gap, and that isn't listed manually, won't be caught. **Tested:** a synthetic series with a split and a 40% overnight drop flags the right windows. On real data (90 days, 18 tickers, run 2026-10-27) it fired on nothing beyond the short-history warm-up, because the TMPV demerger falls outside the 90-day window. So the guard has not yet been exercised on a real corporate action. | 2026-10-27 |
| 13 | **Volume baseline = the prior 20 sessions, excluding today** | Rolling 20 including today | Including today's volume in its own baseline dampens the very spike being detected. Bug found while adding #12. | 2026-10-27 |
| 14 | **Invented data deleted, not relabelled; empty states instead** | Keep as "sample data"; dev-only fixture route | The digest is now built at request time from real pipeline outputs only (`lib/data.ts`). Missing inputs show an explicit empty state. No dev-only fixture route was needed: the real EOD price data is enough to lay out the screen, so none was built. | 2026-10-27 |
| 15 | **Gemini model names and rate limits** | — | *Pending.* Model names will come from the list-models endpoint, and rate limits from the official docs page (URL and date to be recorded here). | — |
| 16 | **BSE scrip codes treated as unverified** | Trust the hard-coded map | The map in `fetch_announcements.py` was written from memory. Slice 1 must confirm each code against BSE before use, especially TMPV after the demerger. | 2026-10-27 |
| 17 | **Drop partial intraday bar before 16:00 IST** | Keep whatever `yfinance` returns | During NSE market hours (`< 16:00 IST`), `yfinance.history()` appends today's incomplete session, comparing partial intraday volume against a full-day 20-session average. `fetch_prices.py` now drops today's row if fetched before 16:00 IST so alerts strictly evaluate settled EOD bars. | 2026-10-27 |
