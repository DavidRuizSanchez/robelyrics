import { type NextRequest, NextResponse } from "next/server";
import { clearAuthCookie } from "@/lib/auth";

async function handleLogout(req: NextRequest) {
  await clearAuthCookie();
  // Detrás de un reverse proxy (Caddy en prod), req.url contiene el host
  // interno del contenedor (p.ej. 0.0.0.0:3000). Usamos x-forwarded-host /
  // x-forwarded-proto cuando estén presentes para que el redirect apunte
  // al host público real.
  const fwdHost = req.headers.get("x-forwarded-host");
  const fwdProto = req.headers.get("x-forwarded-proto");
  if (fwdHost) {
    return NextResponse.redirect(`${fwdProto ?? "https"}://${fwdHost}/`, 303);
  }
  return NextResponse.redirect(new URL("/", req.url), 303);
}

export async function POST(req: NextRequest) {
  return handleLogout(req);
}

export async function GET(req: NextRequest) {
  return handleLogout(req);
}
