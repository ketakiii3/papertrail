import { NextRequest, NextResponse } from "next/server";

// In-memory watchlist for demo
const watchlist: { email: string; ticker: string }[] = [];

export async function GET(req: NextRequest) {
  const email = req.nextUrl.searchParams.get("email");
  if (!email) {
    return NextResponse.json({ error: "Email required" }, { status: 400 });
  }
  const items = watchlist.filter((w) => w.email === email);
  return NextResponse.json(items);
}

export async function POST(req: NextRequest) {
  const body = await req.json();
  const { email, ticker } = body;
  if (!email || !ticker) {
    return NextResponse.json({ error: "Email and ticker required" }, { status: 400 });
  }
  watchlist.push({ email, ticker });
  return NextResponse.json({ status: "added" });
}
