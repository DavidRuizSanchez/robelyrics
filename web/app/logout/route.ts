import { type NextRequest, NextResponse } from "next/server";
import { clearAuthCookie } from "@/lib/auth";

// Allowlist de hosts públicos válidos detrás de Caddy. Sin esto, un atacante
// podría poner X-Forwarded-Host: evilsite.com y conseguir un open-redirect.
// localhost se incluye sólo para dev; en prod nunca llegará a setearse así.
const ALLOWED_HOSTS = new Set([
  "entreinteriores.com",
  "www.entreinteriores.com",
  "localhost:3001",
  "localhost:3000",
  "127.0.0.1:3001",
]);

async function handleLogout(req: NextRequest) {
  await clearAuthCookie();
  // Detrás de un reverse proxy (Caddy en prod), req.url contiene el host
  // interno del contenedor (p.ej. 0.0.0.0:3000). Usamos x-forwarded-host /
  // x-forwarded-proto cuando estén presentes para que el redirect apunte
  // al host público real, validando contra allowlist.
  const fwdHost = req.headers.get("x-forwarded-host");
  const fwdProto = req.headers.get("x-forwarded-proto");
  if (fwdHost && ALLOWED_HOSTS.has(fwdHost)) {
    const proto = fwdProto === "http" ? "http" : "https";
    return NextResponse.redirect(`${proto}://${fwdHost}/`, 303);
  }
  return NextResponse.redirect(new URL("/", req.url), 303);
}

export async function POST(req: NextRequest) {
  return handleLogout(req);
}

export async function GET(req: NextRequest) {
  return handleLogout(req);
}
