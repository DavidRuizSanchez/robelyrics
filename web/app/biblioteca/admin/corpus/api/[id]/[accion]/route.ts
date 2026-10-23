import { NextResponse } from "next/server";
import { apiFetch, ApiError } from "@/lib/api";

// Proxy admin: aprobar, descartar o reintentar un vídeo de la cola de ingesta.
const ACCIONES = new Set(["aprobar", "descartar", "reintentar"]);

export async function POST(
  _request: Request,
  { params }: { params: Promise<{ id: string; accion: string }> },
) {
  const { id, accion } = await params;
  if (!ACCIONES.has(accion)) {
    return NextResponse.json({ error: "Acción desconocida." }, { status: 400 });
  }
  try {
    const data = await apiFetch(`/admin/corpus/queue/${id}/${accion}`, { method: "POST" });
    return NextResponse.json(data);
  } catch (e) {
    const status = e instanceof ApiError ? e.status : 500;
    const msg = status === 409 ? "Ese vídeo ya cambió de estado. Recarga la página." : "No se pudo guardar.";
    return NextResponse.json({ error: msg }, { status });
  }
}
