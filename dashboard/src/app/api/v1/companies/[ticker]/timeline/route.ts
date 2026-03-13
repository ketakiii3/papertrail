import { NextRequest, NextResponse } from "next/server";
import { companies, filings, contradictions, claims } from "../../../data";

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ ticker: string }> }
) {
  const { ticker } = await params;
  const company = companies.find(
    (c) => c.ticker.toLowerCase() === ticker.toLowerCase()
  );
  if (!company) {
    return NextResponse.json({ error: "Company not found" }, { status: 404 });
  }

  const events: { type: string; date: string; data: Record<string, unknown> }[] = [];

  // Add filings
  for (const f of filings.filter((f) => f.company_id === company.id)) {
    events.push({
      type: "filing",
      date: f.filed_at,
      data: { form_type: f.form_type, filing_id: f.id, claim_count: f.claim_count },
    });
  }

  // Add contradictions
  for (const c of contradictions.filter((c) => c.company_id === company.id)) {
    const claimA = claims.find((cl) => cl.id === c.claim_a_id);
    const claimB = claims.find((cl) => cl.id === c.claim_b_id);
    events.push({
      type: "contradiction",
      date: c.created_at.split("T")[0],
      data: {
        severity: c.severity,
        claim_a_text: claimA?.claim_text,
        claim_a_date: claimA?.claim_date,
        claim_b_text: claimB?.claim_text,
        claim_b_date: claimB?.claim_date,
        explanation: c.explanation,
      },
    });
  }

  events.sort((a, b) => b.date.localeCompare(a.date));

  return NextResponse.json({
    ticker: company.ticker,
    company_name: company.name,
    events,
  });
}
