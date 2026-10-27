import { NextResponse } from "next/server";
import { getResearch, getAvailableResearch } from "@/lib/data";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ ticker: string }> }
) {
  const { ticker } = await params;
  const research = getResearch(ticker);

  if (!research) {
    const available = getAvailableResearch();
    const upper = ticker.trim().toUpperCase();
    const normTicker =
      upper.endsWith(".NS") || upper.endsWith(".BO") ? upper : `${upper}.NS`;
    return NextResponse.json(
      {
        error: `Not pre-computed, run \`python pipeline/generate_research.py ${normTicker}\``,
        available,
        hint: `Not pre-computed, run \`python pipeline/generate_research.py ${normTicker}\``,
      },
      { status: 404 }
    );
  }

  return NextResponse.json(research);
}
