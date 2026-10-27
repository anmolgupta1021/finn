"use client";

import { cn, displayTicker, formatChange } from "@/lib/utils";
import type { Alert } from "@/lib/types";
import { Activity, TrendingUp, TrendingDown, Volume2 } from "lucide-react";

export function AlertsBanner({ alerts }: { alerts: Alert[] }) {
  if (!alerts.length) return null;

  return (
    <div className="space-y-1.5">
      {alerts.map((alert, i) => {
        const isVolume = alert.type === "volume_spike";
        const isPositive = alert.type === "price_move" && alert.value > 0;

        return (
          <div
            key={`${alert.ticker}-${alert.type}-${i}`}
            className={cn(
              "flex items-center gap-2 px-3 py-2 rounded-lg text-xs",
              isVolume
                ? "bg-blue-500/10 border border-blue-500/20"
                : isPositive
                ? "bg-green-500/10 border border-green-500/20"
                : "bg-red-500/10 border border-red-500/20"
            )}
          >
            {isVolume ? (
              <Activity
                className="w-3.5 h-3.5 text-blue-400 flex-shrink-0"
              />
            ) : isPositive ? (
              <TrendingUp
                className="w-3.5 h-3.5 text-green-400 flex-shrink-0"
              />
            ) : (
              <TrendingDown
                className="w-3.5 h-3.5 text-red-400 flex-shrink-0"
              />
            )}
            <span className="font-semibold">
              {displayTicker(alert.ticker)}
            </span>
            <span className="text-finn-muted flex-1">{alert.message}</span>
            <span
              className={cn(
                "font-mono text-2xs",
                isVolume
                  ? "text-blue-400"
                  : isPositive
                  ? "text-green-400"
                  : "text-red-400"
              )}
            >
              ₹{alert.close.toLocaleString("en-IN")}
            </span>
          </div>
        );
      })}
    </div>
  );
}
