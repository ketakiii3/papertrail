import { NextRequest, NextResponse } from "next/server";
import { companies, contradictions, buildContradictionResponse } from "../../../data";

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ ticker: string }> }
) {
  const { ticker } = await params;
  const company = companies.find(
    (c) => c.ticker.toLowerCase() === ticker.toLowerCase()
  );
  if (!company) {
    return NextResponse.json({ error: "Company not found" }, { status: 404 });
  }

  const severity = req.nextUrl.searchParams.get("severity");
  let results = contradictions.filter((c) => c.company_id === company.id);
  if (severity) {
    results = results.filter((c) => c.severity === severity);
  }

  return NextResponse.json(results.map(buildContradictionResponse));
}
