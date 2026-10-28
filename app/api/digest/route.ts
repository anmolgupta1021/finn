import { NextRequest, NextResponse } from "next/server";
import { getDigest } from "@/lib/data";
import type { AlertConfig, AnnouncementCategory } from "@/lib/types";

export async function GET(req: NextRequest) {
  const sp = req.nextUrl.searchParams;
  const hoursParam = sp.get("hours");
  const windowHours = hoursParam ? Math.max(1, Number(hoursParam) || 24) : 24;

  const custom: Partial<AlertConfig> = {};
  const vol = sp.get("vol");
  if (vol != null && vol !== "" && Number(vol) > 0) custom.volume_threshold = Number(vol);
  const price = sp.get("price");
  if (price != null && price !== "" && Number(price) > 0) custom.price_move_pct = Number(price);
  const cats = sp.get("cats");
  if (cats != null) {
    custom.watched_categories = cats
      .split(",")
      .map((c) => c.trim())
      .filter(Boolean) as AnnouncementCategory[];
  }

  const digest = getDigest(windowHours, custom);
  return NextResponse.json(digest);
}
