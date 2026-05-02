import { type NextRequest, NextResponse } from "next/server";
import { clearAuthCookie } from "@/lib/auth";

async function handleLogout(req: NextRequest) {
  await clearAuthCookie();
  // URL relativa al host actual (independiente de cómo se exponga el contenedor)
  return NextResponse.redirect(new URL("/login", req.url));
}

export async function POST(req: NextRequest) {
  return handleLogout(req);
}

export async function GET(req: NextRequest) {
  return handleLogout(req);
}
