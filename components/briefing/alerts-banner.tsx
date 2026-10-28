"use client";

import { cn, displayTicker } from "@/lib/utils";
import type { Alert } from "@/lib/types";
import { Activity, ArrowUpRight, FileText, PauseCircle, TrendingDown, TrendingUp } from "lucide-react";

export function AlertsBanner({ alerts }: { alerts: Alert[] }) {
  if (!alerts.length) return null;

  return (
    <div className="space-y-1.5">
      {alerts.map((alert, i) => {
        const paused = alert.type === "volume_unreliable";
        const isVolume = alert.type === "volume_spike";
        const isFiling = alert.type === "material_announcement";
        const isUp = alert.type === "price_move" && alert.value > 0;

        const tone = paused
          ? { box: "bg-finn-surface border border-finn-border", text: "text-finn-muted", Icon: PauseCircle }
          : isFiling
          ? { box: "bg-violet-500/10 border border-violet-500/20", text: "text-violet-300", Icon: FileText }
          : isVolume
          ? { box: "bg-blue-500/10 border border-blue-500/20", text: "text-blue-400", Icon: Activity }
          : isUp
          ? { box: "bg-green-500/10 border border-green-500/20", text: "text-green-400", Icon: TrendingUp }
          : { box: "bg-red-500/10 border border-red-500/20", text: "text-red-400", Icon: TrendingDown };

        return (
          <div
            key={`${alert.ticker}-${alert.type}-${i}`}
            className={cn("flex items-start gap-2 px-3 py-2 rounded-lg text-xs min-w-0", tone.box)}
          >
            <tone.Icon className={cn("w-3.5 h-3.5 flex-shrink-0 mt-0.5", tone.text)} />
            <span className="font-semibold flex-shrink-0">{displayTicker(alert.ticker)}</span>
            <span className="text-finn-muted flex-1 min-w-0 break-words [overflow-wrap:anywhere] line-clamp-3">
              {alert.message}
            </span>
            {isFiling && alert.source_url ? (
              <a
                href={alert.source_url}
                target="_blank"
                rel="noopener noreferrer"
                aria-label="Open filing"
                className={cn("flex-shrink-0", tone.text)}
              >
                <ArrowUpRight className="w-3.5 h-3.5" />
              </a>
            ) : (
              !paused && (
                <span className={cn("font-mono text-2xs flex-shrink-0", tone.text)}>
                  ₹{alert.close.toLocaleString("en-IN")}
                </span>
              )
            )}
          </div>
        );
      })}
    </div>
  );
}
