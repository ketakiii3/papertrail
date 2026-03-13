import { NextRequest, NextResponse } from "next/server";
import { claims, companies } from "../../data";

export async function GET(req: NextRequest) {
  const q = req.nextUrl.searchParams.get("q")?.toLowerCase();
  const limit = parseInt(req.nextUrl.searchParams.get("limit") || "20");

  if (!q || q.length < 3) {
    return NextResponse.json({ error: "Query must be at least 3 characters" }, { status: 400 });
  }

  const results = claims
    .filter(
      (c) =>
        c.claim_text.toLowerCase().includes(q) ||
        (c.topic && c.topic.toLowerCase().includes(q)) ||
        (c.claim_type && c.claim_type.toLowerCase().includes(q))
    )
    .slice(0, limit)
    .map((c) => {
      const company = companies.find((co) => co.id === c.company_id);
      const { company_id, ...claim } = c;
      return {
        claim,
        similarity: 0.85 + Math.random() * 0.14, // Simulated similarity
        company_ticker: company?.ticker || "UNKN",
      };
    });

  return NextResponse.json(results);
}
