import { NextRequest, NextResponse } from "next/server";
import { phoneLoginUrl } from "@/lib/lan";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const host = request.headers.get("host") || "localhost:3000";
  const forwarded = request.headers.get("x-forwarded-proto");
  const protocol = forwarded || request.nextUrl.protocol.replace(":", "");
  const target = await phoneLoginUrl(host, protocol);
  return NextResponse.json(target, { headers: { "Cache-Control": "no-store" } });
}
