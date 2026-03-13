import { NextRequest, NextResponse } from "next/server";
import { companies, claims } from "../../../data";

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

  const limit = parseInt(req.nextUrl.searchParams.get("limit") || "100");
  const companyClaims = claims
    .filter((c) => c.company_id === company.id)
    .slice(0, limit)
    .map(({ company_id, ...rest }) => rest);

  return NextResponse.json(companyClaims);
}
