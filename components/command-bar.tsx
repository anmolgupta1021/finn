"use client";

import { useState } from "react";
import { Search, X } from "lucide-react";
import { cn, displayTicker } from "@/lib/utils";
import type { ResearchData } from "@/lib/types";
import { ResearchPanel } from "@/components/research/research-panel";

// Quick-pick list only. Research availability is decided by the API (404 = not
// generated yet); nothing here claims research exists.
const SUGGESTIONS = [
  { ticker: "INFY.NS", label: "Infosys · 5 transcripts + 5 results filings" },
  { ticker: "RELIANCE.NS", label: "Reliance Industries · 5 transcripts + 5 results filings" },
  { ticker: "TCS.NS", label: "TCS · 5 transcripts + 5 results filings" },
  { ticker: "ICICIBANK.NS", label: "ICICI Bank · 5 transcripts + 5 results filings" },
  { ticker: "ETERNAL.NS", label: "Eternal (formerly Zomato) · 5 transcripts + 5 results filings" },
  { ticker: "PIDILITIND.NS", label: "Pidilite Industries · Cold-ticker test" },
  { ticker: "HDFCBANK.NS", label: "HDFC Bank" },
  { ticker: "BAJFINANCE.NS", label: "Bajaj Finance" },
  { ticker: "ITC.NS", label: "ITC" },
];

export function CommandBar({
  initialResearch = null,
}: {
  initialResearch?: ResearchData | null;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [research, setResearch] = useState<ResearchData | null>(initialResearch);
  const [error, setError] = useState<string | null>(null);

  const filtered = query
    ? SUGGESTIONS.filter(
        (s) =>
          s.label.toLowerCase().includes(query.toLowerCase()) ||
          displayTicker(s.ticker).toLowerCase().includes(query.toLowerCase())
      )
    : SUGGESTIONS;

  async function handleSearch(ticker: string) {
    setLoading(true);
    setError(null);
    try {
      const clean = ticker.trim().toUpperCase();
      const symbol = clean.replace(/\.(NS|BO)$/, "");
      const normTicker =
        clean.endsWith(".NS") || clean.endsWith(".BO") ? clean : `${symbol}.NS`;
      const res = await fetch(`/api/research/${symbol}`);
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        if (res.status === 404) {
          throw new Error(
            body.error ||
              `Not pre-computed, run \`python pipeline/generate_research.py ${normTicker}\``
          );
        }
        throw new Error(body.error || "Research request failed");
      }
      const data = await res.json();
      setResearch(data);
      setIsOpen(false);
      setQuery("");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load research");
    } finally {
      setLoading(false);
    }
  }

  if (research) {
    return (
      <ResearchPanel
        data={research}
        onClose={() => setResearch(null)}
      />
    );
  }

  return (
    <>
      {/* Floating command bar trigger */}
      <div className="fixed bottom-0 left-0 right-0 max-w-[430px] mx-auto p-3 z-40">
        <button
          onClick={() => setIsOpen(true)}
          className={cn(
            "w-full flex items-center gap-2 px-4 py-3 rounded-xl",
            "bg-finn-card border border-finn-border",
            "text-finn-muted text-sm",
            "shadow-lg shadow-black/40",
            "active:scale-[0.98] transition-transform"
          )}
        >
          <Search className="w-4 h-4" />
          <span>Research any company...</span>
        </button>
      </div>

      {/* Full-screen search panel */}
      {isOpen && (
        <div className="fixed inset-0 z-50 bg-finn-bg flex flex-col max-w-[430px] mx-auto">
          {/* Search input */}
          <div className="flex items-center gap-2 px-4 py-3 border-b border-finn-border">
            <Search className="w-4 h-4 text-finn-muted flex-shrink-0" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search ticker or company name..."
              className="flex-1 bg-transparent text-sm text-finn-text placeholder:text-finn-muted outline-none"
              autoFocus
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  if (filtered.length > 0) {
                    handleSearch(filtered[0].ticker);
                  } else if (query.trim()) {
                    handleSearch(query.trim());
                  }
                }
              }}
            />
            <button
              onClick={() => {
                setIsOpen(false);
                setQuery("");
                setError(null);
              }}
              className="w-6 h-6 rounded-full bg-finn-surface flex items-center justify-center"
            >
              <X className="w-3.5 h-3.5 text-finn-muted" />
            </button>
          </div>

          {/* Error */}
          {error && (
            <div className="mx-4 mt-3 px-3 py-2 rounded-lg bg-amber-500/10 border border-amber-500/30 text-xs text-amber-300 font-mono">
              {error}
            </div>
          )}

          {/* Loading */}
          {loading && (
            <div className="flex items-center justify-center py-12">
              <div className="w-6 h-6 border-2 border-finn-accent border-t-transparent rounded-full animate-spin" />
              <span className="ml-2 text-sm text-finn-muted">
                Analyzing...
              </span>
            </div>
          )}

          {/* Suggestions */}
          {!loading && (
            <div className="flex-1 overflow-y-auto p-4">
              <div className="finn-section-title">
                {query ? "Results" : "Quick research"}
              </div>
              <div className="space-y-1">
                {filtered.map((s) => (
                  <button
                    key={s.ticker}
                    onClick={() => handleSearch(s.ticker)}
                    className={cn(
                      "w-full flex items-center justify-between px-3 py-2.5 rounded-lg",
                      "hover:bg-finn-surface active:bg-finn-card transition-colors",
                      "text-left"
                    )}
                  >
                    <div>
                      <span className="text-sm font-medium">
                        {displayTicker(s.ticker)}
                      </span>
                      <span className="text-xs text-finn-muted ml-2">
                        {s.label}
                      </span>
                    </div>
                    <Search className="w-3.5 h-3.5 text-finn-muted" />
                  </button>
                ))}
              </div>
              {filtered.length === 0 && query.trim() && (
                <button
                  onClick={() => handleSearch(query.trim())}
                  className="w-full flex items-center justify-between px-3 py-2.5 rounded-lg bg-finn-surface hover:bg-finn-card transition-colors text-left"
                >
                  <div>
                    <span className="text-sm font-medium">
                      {displayTicker(query.trim().toUpperCase())}
                    </span>
                    <span className="text-xs text-finn-muted ml-2">
                      Lookup ticker ({query.trim().toUpperCase()})
                    </span>
                  </div>
                  <Search className="w-3.5 h-3.5 text-finn-muted" />
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </>
  );
}
