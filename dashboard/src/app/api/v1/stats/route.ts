import { NextResponse } from "next/server";
import { companies, filings, claims, contradictions } from "../data";

export async function GET() {
  const byS: Record<string, number> = { critical: 0, high: 0, medium: 0, low: 0 };
  for (const c of contradictions) byS[c.severity] = (byS[c.severity] || 0) + 1;

  return NextResponse.json({
    total_companies: companies.length,
    total_filings: filings.length,
    total_claims: claims.length,
    total_contradictions: contradictions.length,
    contradictions_by_severity: byS,
  });
}
