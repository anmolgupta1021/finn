import { NextResponse } from "next/server";
import { getDigest } from "@/lib/data";

export async function GET() {
  const digest = getDigest();
  if (!digest) {
    return NextResponse.json({ error: "No digest data available" }, { status: 404 });
  }
  return NextResponse.json(digest);
}
