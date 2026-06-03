import { cookies } from "next/headers";
import { NextResponse } from "next/server";

// Proxy autenticado hacia /playlists/* del API. La cookie HttpOnly la añade
// el servidor; el navegador nunca ve la URL del API ni el token. Restringido
// al prefijo /playlists para que no sea un proxy abierto.

const API_BASE = process.env.API_INTERNAL_URL || "http://api:8000";
const TOKEN_COOKIE = "robelyrics_token";

async function forward(req: Request, path: string[] | undefined, method: string) {
  const token = (await cookies()).get(TOKEN_COOKIE)?.value;
  const suffix = path && path.length ? `/${path.join("/")}` : "";
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;

  let body: string | undefined;
  if (method !== "GET") {
    const text = await req.text();
    body = text || undefined;
  }

  const res = await fetch(`${API_BASE}/playlists${suffix}`, {
    method,
    headers,
    body,
    cache: "no-store",
  });

  const text = await res.text();
  if (!res.ok) {
    let detail: unknown = text;
    try {
      detail = JSON.parse(text);
    } catch {
      // queda como texto
    }
    return NextResponse.json({ error: detail }, { status: res.status });
  }
  if (!text) return new NextResponse(null, { status: res.status });
  return new NextResponse(text, {
    status: res.status,
    headers: { "Content-Type": "application/json" },
  });
}

type Ctx = { params: Promise<{ path?: string[] }> };

export async function GET(req: Request, { params }: Ctx) {
  return forward(req, (await params).path, "GET");
}
export async function POST(req: Request, { params }: Ctx) {
  return forward(req, (await params).path, "POST");
}
export async function DELETE(req: Request, { params }: Ctx) {
  return forward(req, (await params).path, "DELETE");
}
