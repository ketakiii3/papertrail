import { NextRequest, NextResponse } from "next/server";
import { surveillanceFlags } from "../../data";

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const flag = surveillanceFlags.find((f) => f.id === Number(id));
  if (!flag) {
    return NextResponse.json({ error: "Flag not found" }, { status: 404 });
  }
  return NextResponse.json(flag);
}
