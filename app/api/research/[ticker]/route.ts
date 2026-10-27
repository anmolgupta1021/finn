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
    return NextResponse.json(
      {
        error: `No research data for ${ticker}`,
        available,
        hint: "Try one of the available tickers, or run the pipeline to generate data.",
      },
      { status: 404 }
    );
  }

  return NextResponse.json(research);
}
