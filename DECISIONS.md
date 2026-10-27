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
