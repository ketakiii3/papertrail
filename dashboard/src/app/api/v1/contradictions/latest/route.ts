import { NextRequest, NextResponse } from "next/server";
import { contradictions, buildContradictionResponse } from "../../data";

export async function GET(req: NextRequest) {
  const severity = req.nextUrl.searchParams.get("severity");
  const limit = parseInt(req.nextUrl.searchParams.get("limit") || "20");

  let results = [...contradictions];
  if (severity) {
    results = results.filter((c) => c.severity === severity);
  }

  // Sort by created_at desc
  results.sort((a, b) => b.created_at.localeCompare(a.created_at));

  return NextResponse.json(results.slice(0, limit).map(buildContradictionResponse));
}
