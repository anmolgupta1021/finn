"use client";

import { useState } from "react";
import { X } from "lucide-react";
import type { AlertConfig, AnnouncementCategory } from "@/lib/types";
import { cn } from "@/lib/utils";

export const ALERT_CONFIG_STORAGE_KEY = "finn_alert_config";

const CATEGORY_OPTIONS: { value: AnnouncementCategory; label: string }[] = [
  { value: "results", label: "Results" },
  { value: "management_change", label: "Management change" },
  { value: "M&A", label: "M&A" },
  { value: "dividend", label: "Dividend" },
  { value: "litigation", label: "Litigation / orders" },
  { value: "insider_trading", label: "Insider trading" },
  { value: "fund_raise", label: "Fund raise" },
  { value: "bonus_split", label: "Bonus / split / buyback" },
  { value: "credit_rating", label: "Credit rating" },
  { value: "capex", label: "Capex / orders" },
];

const VOL_PRESETS = [1.5, 2, 2.5, 3];
const PRICE_PRESETS = [2, 3, 5];

export function loadStoredAlertConfig(): Partial<AlertConfig> | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(ALERT_CONFIG_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Partial<AlertConfig>) : null;
  } catch {
    return null;
  }
}

export function AlertSettingsPanel({
  config,
  onSave,
  onClose,
}: {
  config: AlertConfig;
  onSave: (cfg: AlertConfig) => void;
  onClose: () => void;
}) {
  const [vol, setVol] = useState<string>(String(config.volume_threshold));
  const [price, setPrice] = useState<string>(String(config.price_move_pct));
  const [cats, setCats] = useState<Set<AnnouncementCategory>>(new Set(config.watched_categories));

  const volNum = Number(vol);
  const priceNum = Number(price);
  const valid = volNum > 0 && volNum <= 50 && priceNum > 0 && priceNum <= 50;

  function toggleCat(c: AnnouncementCategory) {
    const next = new Set(cats);
    if (next.has(c)) next.delete(c);
    else next.add(c);
    setCats(next);
  }

  function save() {
    if (!valid) return;
    const cfg: AlertConfig = {
      volume_threshold: volNum,
      price_move_pct: priceNum,
      watched_categories: Array.from(cats),
    };
    try {
      window.localStorage.setItem(ALERT_CONFIG_STORAGE_KEY, JSON.stringify(cfg));
    } catch {
      /* storage unavailable: still apply for this session */
    }
    onSave(cfg);
  }

  return (
    <div
      role="dialog"
      aria-label="Alert settings"
      className="mx-4 mb-4 rounded-xl border border-finn-border bg-finn-surface p-3"
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-semibold">Alert settings</span>
        <button onClick={onClose} aria-label="Close settings" className="p-1">
          <X className="w-3.5 h-3.5 text-finn-muted" />
        </button>
      </div>

      <label className="block text-2xs text-finn-muted mb-1">
        Volume spike: alert when volume ≥ N × prior 20-day average
      </label>
      <div className="flex items-center gap-1 flex-wrap mb-3">
        {VOL_PRESETS.map((v) => (
          <button
            key={v}
            onClick={() => setVol(String(v))}
            className={cn(
              "px-2 py-0.5 rounded text-2xs font-mono border",
              Number(vol) === v ? "bg-finn-accent text-white border-finn-accent" : "border-finn-border text-finn-muted"
            )}
          >
            {v}×
          </button>
        ))}
        <input
          type="number"
          inputMode="decimal"
          min={0.1}
          step={0.1}
          value={vol}
          onChange={(e) => setVol(e.target.value)}
          aria-label="Volume multiple N"
          className="w-16 px-1.5 py-0.5 rounded bg-transparent border border-finn-border text-2xs font-mono"
        />
      </div>

      <label className="block text-2xs text-finn-muted mb-1">
        Price move: alert when daily close-to-close move ≥ ±X%
      </label>
      <div className="flex items-center gap-1 flex-wrap mb-3">
        {PRICE_PRESETS.map((p) => (
          <button
            key={p}
            onClick={() => setPrice(String(p))}
            className={cn(
              "px-2 py-0.5 rounded text-2xs font-mono border",
              Number(price) === p ? "bg-finn-accent text-white border-finn-accent" : "border-finn-border text-finn-muted"
            )}
          >
            ±{p}%
          </button>
        ))}
        <input
          type="number"
          inputMode="decimal"
          min={0.1}
          step={0.1}
          value={price}
          onChange={(e) => setPrice(e.target.value)}
          aria-label="Price move percent X"
          className="w-16 px-1.5 py-0.5 rounded bg-transparent border border-finn-border text-2xs font-mono"
        />
      </div>

      <div className="text-2xs text-finn-muted mb-1">Alert on filings of these types</div>
      <div className="grid grid-cols-2 gap-x-2 gap-y-1 mb-3">
        {CATEGORY_OPTIONS.map((c) => (
          <label key={c.value} className="flex items-center gap-1.5 text-2xs">
            <input
              type="checkbox"
              checked={cats.has(c.value)}
              onChange={() => toggleCat(c.value)}
            />
            <span>{c.label}</span>
          </label>
        ))}
      </div>

      <div className="flex items-center justify-between">
        <span className="text-2xs text-finn-muted">Saved in this browser.</span>
        <button
          onClick={save}
          disabled={!valid}
          className="px-3 py-1 rounded bg-finn-accent text-white text-2xs font-semibold disabled:opacity-40"
        >
          Apply
        </button>
      </div>
    </div>
  );
}
