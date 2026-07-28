import { NextResponse } from "next/server";
import { apiFetch, ApiError } from "@/lib/api";

// Proxy del alta manual desde URL.
//   POST → /admin/proposals/from-url  (encola y responde 202 al momento)
//   GET  → /admin/ingest-jobs?limit=N  (estado de los últimos trabajos)
//
// El trabajo real tarda 2-4 min y Cloudflare corta a los 100 s, así que NO se
// espera aquí: corre en el servidor y el panel pregunta por él. Por eso este
// handler es rápido y no necesita maxDuration largo.
// Body del POST: { url, topic?, body_text?, rewrite?, force? }.

function unwrap(e: unknown) {
  if (e instanceof ApiError) {
    const detail =
      typeof e.detail === "object" && e.detail !== null && "detail" in e.detail
        ? (e.detail as { detail: unknown }).detail
        : e.detail;
    if (typeof detail === "object" && detail !== null) {
      return NextResponse.json(detail, { status: e.status });
    }
    return NextResponse.json({ error: String(detail) }, { status: e.status });
  }
  return NextResponse.json({ error: "error interno" }, { status: 500 });
}

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "body no válido" }, { status: 400 });
  }
  try {
    const data = await apiFetch<unknown>("/admin/proposals/from-url", {
      method: "POST",
      body,
    });
    return NextResponse.json(data, { status: 202 });
  } catch (e) {
    return unwrap(e);
  }
}

export async function GET(request: Request) {
  const limit = new URL(request.url).searchParams.get("limit") || "5";
  try {
    const data = await apiFetch<unknown>(
      `/admin/ingest-jobs?limit=${encodeURIComponent(limit)}`,
    );
    return NextResponse.json(data);
  } catch (e) {
    return unwrap(e);
  }
}
