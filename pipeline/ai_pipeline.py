"""
FINN Pipeline — AI processing layer.

Uses Gemini for:
- Announcement classification (Flash)
- Summary generation (Flash)
- Results number extraction (Flash)
- Deep company analysis (Pro)

Every call is cached by content hash and logged for cost tracking.
"""

import json
import os
import google.generativeai as genai
from config import (
    ANNOUNCEMENT_CATEGORIES, CATEGORY_PRIORITY,
    content_hash, get_cached, set_cache, log_llm_call,
    ANN_DIR, RESEARCH_DIR, save_json, load_json, ticker_symbol,
    ALL_TICKERS, PORTFOLIO_TICKERS,
)

# ─── Model setup ─────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

MODEL_FLASH = "gemini-2.0-flash"
MODEL_PRO = "gemini-2.5-pro-preview-05-06"


def call_gemini(
    prompt: str,
    model_name: str = MODEL_FLASH,
    task: str = "generic",
    ticker: str = "",
    response_mime_type: str = "application/json",
) -> dict | str:
    """
    Call Gemini with caching and logging.
    Returns parsed JSON if response_mime_type is application/json, else raw text.
    """
    chash = content_hash(prompt)

    # Check cache
    cached = get_cached(chash, task)
    if cached is not None:
        log_llm_call(task, ticker, model_name, 0, 0, chash, cache_hit=True)
        print(f"  💨 Cache hit for {task}/{ticker}")
        return cached

    # Call Gemini
    model = genai.GenerativeModel(model_name)
    generation_config = {}
    if response_mime_type == "application/json":
        generation_config["response_mime_type"] = "application/json"

    response = model.generate_content(
        prompt,
        generation_config=generation_config if generation_config else None,
    )

    # Parse response
    text = response.text
    tokens_in = response.usage_metadata.prompt_token_count if hasattr(response, 'usage_metadata') else 0
    tokens_out = response.usage_metadata.candidates_token_count if hasattr(response, 'usage_metadata') else 0

    if response_mime_type == "application/json":
        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            # Try to extract JSON from the response
            import re
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                result = json.loads(match.group())
            else:
                result = {"raw": text}
    else:
        result = text

    # Cache and log
    set_cache(chash, task, result)
    log_llm_call(task, ticker, model_name, tokens_in, tokens_out, chash, cache_hit=False)
    print(f"  🤖 {model_name} → {tokens_in}+{tokens_out} tokens")

    return result


# ─── Classification ──────────────────────────────────────────────────────────

CLASSIFY_PROMPT = """You are a financial analyst classifying corporate announcements filed with Indian stock exchanges (BSE/NSE).

Given this announcement headline, classify it into EXACTLY ONE category from this list:
{categories}

Also assign a priority:
- 1 = Material, likely moves the stock (results, M&A, management change, litigation)
- 2 = Significant but expected (dividend, fund raise, capex, credit rating, earnings call, pledging)
- 3 = Routine compliance/paperwork (ESOP, AGM, postal ballot, unclassified)

Write a ONE-LINE "so what" summary for an investor. Be specific and concise. If it's routine, say so.

Announcement headline: "{headline}"
Company: {company}

Respond in JSON:
{{"category": "...", "priority": 1|2|3, "summary": "..."}}
"""


def classify_announcement(announcement: dict) -> dict:
    """Classify a single announcement using Gemini Flash."""
    prompt = CLASSIFY_PROMPT.format(
        categories=", ".join(ANNOUNCEMENT_CATEGORIES),
        headline=announcement["headline"],
        company=announcement.get("company_name", announcement["ticker"]),
    )
    result = call_gemini(
        prompt, MODEL_FLASH, task="classify", ticker=announcement["ticker"]
    )
    return result


# ─── Results extraction ─────────────────────────────────────────────────────

EXTRACT_RESULTS_PROMPT = """You are a financial analyst extracting quarterly results from an Indian listed company's results filing.

Extract these four numbers for the CURRENT quarter:
- Revenue (total income from operations)
- EBITDA (or operating profit as proxy)
- PBT (profit before tax)
- PAT (profit after tax / net profit)

For each, provide:
- The absolute value in crores (₹ Cr)
- QoQ change % (vs previous quarter) if available
- YoY change % (vs same quarter last year) if available

Filing text:
\"\"\"
{filing_text}
\"\"\"

Company: {company}

Respond in JSON:
{{
  "quarter": "Q2FY27",
  "revenue": {{"value": 24000, "qoq": 3.2, "yoy": 8.1}},
  "ebitda": {{"value": 4500, "qoq": 4.1, "yoy": 9.3}},
  "pbt": {{"value": 2600, "qoq": 2.8, "yoy": 11.0}},
  "pat": {{"value": 1980, "qoq": 3.0, "yoy": 12.2}},
  "highlights": "One-line key takeaway"
}}

If a number is not available, use null. Be precise — use the exact numbers from the filing.
"""


def extract_results(filing_text: str, company: str, ticker: str) -> dict:
    """Extract quarterly results numbers from a results filing."""
    prompt = EXTRACT_RESULTS_PROMPT.format(
        filing_text=filing_text[:8000],  # Limit input size
        company=company,
    )
    return call_gemini(prompt, MODEL_FLASH, task="extract_results", ticker=ticker)


# ─── Narrative vs Numbers (Pro model) ───────────────────────────────────────

NARRATIVE_VS_NUMBERS_PROMPT = """You are a senior equity analyst comparing what management SAID they would deliver versus what they ACTUALLY delivered, using primary sources only.

You have the last 4 quarters of:
1. Concall transcripts — where management gives guidance and commentary
2. Quarterly results filings — the actual numbers

For each quarter, identify:
- What management explicitly guided on (revenue growth, margins, capex, etc.)
- What was actually delivered
- Whether it was a HIT, MISS, or BEAT

Be specific: quote the guidance with source (e.g., "Q4FY26 concall, p.14: 'We expect 15% revenue growth'") and compare to the actual number.

This is the difference between summarising management and ANALYSING them. Be direct. No AI slop.

Company: {company}
Ticker: {ticker}

Source documents:
{documents}

Respond in JSON:
{{
  "summary": "2-3 sentence verdict on management credibility",
  "quarters": [
    {{
      "quarter": "Q1FY27",
      "guided": [
        {{
          "metric": "Revenue growth",
          "guidance": "15% YoY growth",
          "source": "Q4FY26 concall transcript, page 14"
        }}
      ],
      "delivered": [
        {{
          "metric": "Revenue growth",
          "actual": "9.2% YoY",
          "source": "Q1FY27 results filing, page 1"
        }}
      ],
      "verdict": "miss",
      "commentary": "Management attributed shortfall to..."
    }}
  ],
  "credibility_score": "high|medium|low",
  "pattern": "Description of any pattern in hits/misses"
}}
"""


def analyze_narrative_vs_numbers(
    company: str, ticker: str, documents: list[dict]
) -> dict:
    """
    Run narrative-vs-numbers analysis using Gemini Pro.
    documents: list of {type, quarter, text, pages} dicts.
    """
    # Format documents for the prompt
    doc_text = ""
    for doc in documents:
        doc_text += f"\n--- {doc['type']} ({doc.get('quarter', doc.get('year', ''))}) ---\n"
        doc_text += doc["text"][:15000]  # Limit per document
        doc_text += "\n"

    prompt = NARRATIVE_VS_NUMBERS_PROMPT.format(
        company=company,
        ticker=ticker,
        documents=doc_text[:60000],  # Total limit for Pro context
    )
    return call_gemini(
        prompt, MODEL_PRO, task="narrative_vs_numbers", ticker=ticker
    )


# ─── Batch processing ───────────────────────────────────────────────────────

def classify_all_announcements(tickers: list[str] = None) -> None:
    """Classify all cached announcements using Gemini Flash."""
    tickers = tickers or ALL_TICKERS

    for ticker in tickers:
        sym = ticker_symbol(ticker)
        path = ANN_DIR / f"{sym}.json"
        if not path.exists():
            continue

        announcements = load_json(path)
        print(f"🏷️  Classifying {len(announcements)} announcements for {sym}...")

        for ann in announcements:
            if ann["category"] != "unclassified" and ann["summary"]:
                continue  # Already classified

            result = classify_announcement(ann)
            ann["category"] = result.get("category", "unclassified")
            ann["priority"] = result.get("priority", CATEGORY_PRIORITY.get(ann["category"], 3))
            ann["summary"] = result.get("summary", "")

        save_json(path, announcements)


if __name__ == "__main__":
    print("=" * 60)
    print("FINN — AI Pipeline")
    print("=" * 60)
    classify_all_announcements()
    print("Done.")
