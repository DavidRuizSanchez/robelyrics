import { NextResponse } from "next/server";
import { apiFetch, ApiError } from "@/lib/api";

// Proxy admin: marcar como vistos uno o varios cambios del monitor.
export async function POST(request: Request) {
  const body = (await request.json().catch(() => ({}))) as { ids?: unknown };
  const ids = Array.isArray(body.ids) ? body.ids.filter((x): x is number => Number.isInteger(x)) : [];
  if (ids.length === 0) {
    return NextResponse.json({ error: "No hay nada que marcar." }, { status: 400 });
  }
  try {
    const data = await apiFetch("/admin/cambios/visto", {
      method: "POST",
      body: { ids },
    });
    return NextResponse.json(data);
  } catch (e) {
    const status = e instanceof ApiError ? e.status : 500;
    return NextResponse.json({ error: "No se pudo guardar." }, { status });
  }
}
