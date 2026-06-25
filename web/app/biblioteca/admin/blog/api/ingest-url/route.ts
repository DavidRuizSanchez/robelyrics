import { NextResponse } from "next/server";
import { apiFetch, ApiError } from "@/lib/api";

// Proxy POST → /admin/proposals/from-url.
// Body: { url: string, topic?: string, rewrite?: boolean, force?: boolean }.
// La reescritura editorial investiga + escribe + verifica, así que puede tardar
// 1-2 min: dejamos que el route handler corra el tiempo que haga falta.
export const maxDuration = 300;

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
    return NextResponse.json(data);
  } catch (e) {
    if (e instanceof ApiError) {
      // FastAPI devuelve { detail: "..." }; desempaquétalo para el aviso.
      const detail =
        typeof e.detail === "object" && e.detail !== null && "detail" in e.detail
          ? (e.detail as { detail: unknown }).detail
          : e.detail;
      return NextResponse.json({ error: String(detail) }, { status: e.status });
    }
    return NextResponse.json({ error: "error interno" }, { status: 500 });
  }
}
