import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Format a number in Indian notation (lakhs/crores).
 * e.g., 240000 → "₹2.4L Cr", 19800 → "₹19,800 Cr"
 */
export function formatIndianCurrency(crores: number): string {
  if (crores >= 100000) {
    return `₹${(crores / 100000).toFixed(1)}L Cr`;
  }
  if (crores >= 1000) {
    return `₹${(crores / 1000).toFixed(1)}K Cr`;
  }
  return `₹${crores.toLocaleString("en-IN")} Cr`;
}

/**
 * Format a percentage change with + or - prefix and color class.
 */
export function formatChange(pct: number | null | undefined): {
  text: string;
  className: string;
} {
  if (pct == null) return { text: "—", className: "text-finn-muted" };
  const sign = pct >= 0 ? "+" : "";
  return {
    text: `${sign}${pct.toFixed(1)}%`,
    className: pct >= 0 ? "text-positive" : "text-negative",
  };
}

/**
 * Format a ticker symbol for display.
 * "RELIANCE.NS" → "RELIANCE"
 */
export function displayTicker(ticker: string): string {
  return ticker.replace(/\.(NS|BO)$/, "");
}

/**
 * Relative time display.
 * e.g., "2h ago", "yesterday", "3d ago"
 */
export function timeAgo(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays === 1) return "yesterday";
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}

/**
 * Priority label and color.
 */
export function priorityMeta(priority: number): {
  label: string;
  color: string;
  dot: string;
} {
  switch (priority) {
    case 1:
      return { label: "Material", color: "finn-badge-red", dot: "bg-red-400" };
    case 2:
      return {
        label: "Notable",
        color: "finn-badge-amber",
        dot: "bg-amber-400",
      };
    default:
      return {
        label: "Routine",
        color: "finn-badge-muted",
        dot: "bg-finn-muted",
      };
  }
}
