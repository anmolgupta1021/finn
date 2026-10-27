"use client";

import { useState } from "react";
import { cn, displayTicker, formatChange } from "@/lib/utils";
import type { PortfolioTicker } from "@/lib/types";

export function PortfolioStrip({
  tickers,
}: {
  tickers: PortfolioTicker[];
}) {
  return (
    <div className="flex gap-1.5 overflow-x-auto no-scrollbar py-1 px-1">
      {tickers.map((t) => {
        const { text, className } = formatChange(t.change_pct);
        const hasEvent = t.has_announcement;
        return (
          <div
            key={t.ticker}
            className={cn(
              "flex-shrink-0 flex items-center gap-1 px-2 py-1 rounded-lg text-xs",
              "bg-finn-surface border border-finn-border",
              hasEvent && "border-finn-accent/40"
            )}
          >
            {hasEvent && (
              <span className="w-1.5 h-1.5 rounded-full bg-finn-accent animate-pulse" />
            )}
            <span className="font-medium text-finn-text">
              {displayTicker(t.ticker)}
            </span>
            <span className={cn("font-mono text-2xs", className)}>
              {text}
            </span>
          </div>
        );
      })}
    </div>
  );
}
