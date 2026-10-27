import { NextRequest, NextResponse } from "next/server";
import { getDigest } from "@/lib/data";

export async function GET(req: NextRequest) {
  const hoursParam = req.nextUrl.searchParams.get("hours");
  const windowHours = hoursParam ? Math.max(1, Number(hoursParam) || 24) : 24;
  const digest = getDigest(windowHours);
  return NextResponse.json(digest);
}
