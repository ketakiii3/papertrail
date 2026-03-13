import { NextRequest, NextResponse } from "next/server";
import { companies } from "../data";

export async function GET(req: NextRequest) {
  const search = req.nextUrl.searchParams.get("search")?.toLowerCase();
  const limit = parseInt(req.nextUrl.searchParams.get("limit") || "50");

  let results = companies;
  if (search) {
    results = companies.filter(
      (c) =>
        c.ticker.toLowerCase().includes(search) ||
        c.name.toLowerCase().includes(search)
    );
  }

  return NextResponse.json(results.slice(0, limit));
}
