import { NextResponse } from "next/server";
import { apiFetch, ApiError } from "@/lib/api";

// Proxy admin: relanzar el Motor de Consenso sobre una errata e intentar aplicarla.
// Consulta fuentes externas (LRCLIB, letras.com, Wikipedia) + juez LLM: puede tardar.
export const maxDuration = 120;

export async function POST(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  try {
    const data = await apiFetch(`/errata/admin/${id}/fix`, { method: "POST" });
    return NextResponse.json(data);
  } catch (e) {
    const status = e instanceof ApiError ? e.status : 500;
    return NextResponse.json({ error: "No se pudo verificar." }, { status });
  }
}
