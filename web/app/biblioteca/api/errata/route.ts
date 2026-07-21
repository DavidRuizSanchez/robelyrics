import { NextResponse } from "next/server";
import { apiFetch, ApiError } from "@/lib/api";

// Proxy autenticado para reportar una errata (letra/autoría/disco/interpretación).
// La cookie HttpOnly la añade apiFetch server-side.

type ErrataBody = {
  target_type?: string;
  target_id?: number | null;
  field?: string | null;
  reported_wrong?: string | null;
  suggested_right?: string | null;
  note?: string | null;
};

export async function POST(request: Request) {
  let body: ErrataBody;
  try {
    body = (await request.json()) as ErrataBody;
  } catch {
    return NextResponse.json({ error: "Datos no válidos." }, { status: 400 });
  }
  if (!body.target_type) {
    return NextResponse.json({ error: "Falta el tipo de errata." }, { status: 400 });
  }
  try {
    const data = await apiFetch<{ id: number; status: string; message: string }>("/errata", {
      method: "POST",
      body,
    });
    return NextResponse.json(data);
  } catch (e) {
    if (e instanceof ApiError) {
      if (e.status === 401) {
        return NextResponse.json({ error: "Regístrate para avisar." }, { status: 401 });
      }
      return NextResponse.json({ error: "No se pudo enviar el aviso." }, { status: e.status });
    }
    return NextResponse.json({ error: "Error inesperado." }, { status: 500 });
  }
}
