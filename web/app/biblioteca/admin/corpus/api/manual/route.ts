import { NextResponse } from "next/server";
import { apiFetch, ApiError } from "@/lib/api";

// Proxy admin: añadir una URL al corpus a mano.
export async function POST(request: Request) {
  const body = await request.json().catch(() => ({}));
  try {
    const data = await apiFetch("/admin/corpus/queue/manual", { method: "POST", body });
    return NextResponse.json(data);
  } catch (e) {
    const status = e instanceof ApiError ? e.status : 500;
    // FastAPI manda {detail: "..."}; en un 422 de validación, detail es una lista.
    const detail = e instanceof ApiError ? (e.detail as { detail?: unknown })?.detail : null;
    const msg =
      typeof detail === "string" ? detail : status === 422 ? "Revisa la URL y el tipo." : "No se pudo añadir.";
    return NextResponse.json({ error: msg }, { status });
  }
}
