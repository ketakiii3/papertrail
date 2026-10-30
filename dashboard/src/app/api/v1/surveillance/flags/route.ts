import { NextRequest, NextResponse } from "next/server";
import { surveillanceFlags } from "../data";

export async function GET(req: NextRequest) {
  const flagged = req.nextUrl.searchParams.get("flagged");
  const ticker = req.nextUrl.searchParams.get("ticker")?.toUpperCase();
  const limit = parseInt(req.nextUrl.searchParams.get("limit") || "50");

  let results = surveillanceFlags;
  if (flagged !== null) results = results.filter((f) => f.flagged === (flagged === "true"));
  if (ticker) results = results.filter((f) => f.ticker === ticker);

  // List view omits the per-day series, like the real API
  return NextResponse.json(results.slice(0, limit).map(({ daily_ar: _daily, ...rest }) => rest));
}
