import { NextResponse } from "next/server";
import { apiFetch, ApiError } from "@/lib/api";

// Proxy admin del panel «Relaciones y entidades» (plan de relaciones, 18-11-2026).
const ACCIONES: Record<string, Set<string>> = {
  propuesta: new Set(["aprobar", "descartar", "recuperar"]),
  relacion: new Set(["aprobar", "rechazar"]),
};

export async function POST(
  _request: Request,
  { params }: { params: Promise<{ tipo: string; id: string; accion: string }> },
) {
  const { tipo, id, accion } = await params;
  if (!ACCIONES[tipo]?.has(accion)) {
    return NextResponse.json({ error: "Acción desconocida." }, { status: 400 });
  }
  try {
    const data = await apiFetch(`/admin/entidades/${tipo}/${id}/${accion}`, { method: "POST" });
    return NextResponse.json(data);
  } catch (e) {
    const status = e instanceof ApiError ? e.status : 500;
    const msg = status === 409 ? "Ya cambió de estado. Recarga la página." : "No se pudo guardar.";
    return NextResponse.json({ error: msg }, { status });
  }
}
