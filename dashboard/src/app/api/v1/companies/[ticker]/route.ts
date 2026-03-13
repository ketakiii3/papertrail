import { NextRequest, NextResponse } from "next/server";
import { companies } from "../../data";

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
  return NextResponse.json(company);
}
