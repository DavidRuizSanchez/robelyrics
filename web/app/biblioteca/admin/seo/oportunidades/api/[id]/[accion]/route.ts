import { NextResponse } from "next/server";
import { apiFetch, ApiError } from "@/lib/api";

// Proxy admin: mover una oportunidad SEO (approve | apply | discard).
export async function POST(
  _request: Request,
  { params }: { params: Promise<{ id: string; accion: string }> },
) {
  const { id, accion } = await params;
  if (!["approve", "apply", "discard"].includes(accion)) {
    return NextResponse.json({ error: "Acción no válida." }, { status: 400 });
  }
  try {
    const data = await apiFetch(`/admin/seo-opportunities/${id}/${accion}`, { method: "POST" });
    return NextResponse.json(data);
  } catch (e) {
    const status = e instanceof ApiError ? e.status : 500;
    // El 409 trae el motivo real (el contenido cambió bajo el borrador, estado
    // que no toca); enseñarlo tal cual evita el clásico "el botón no hace nada".
    const detail =
      e instanceof ApiError && typeof e.detail === "object" && e.detail !== null
        ? String((e.detail as { detail?: string }).detail ?? "")
        : "";
    return NextResponse.json({ error: detail || "No se pudo completar." }, { status });
  }
}
