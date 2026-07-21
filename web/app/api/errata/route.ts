import { NextResponse } from "next/server";
import { apiFetch, ApiError } from "@/lib/api";

// Proxy de reporte de erratas para TODO el site (público incluido). apiFetch
// añade la cookie server-side si la hay: si el usuario está logueado, la API
// anota quién; si no, la errata queda igualmente como anónima/pending.

type ErrataBody = {
  target_type?: string;
  target_id?: number | null;
  field?: string | null;
  page_ref?: string | null;
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
  if (!body.target_type) body.target_type = "content";
  try {
    const data = await apiFetch<{ id: number; status: string; message: string }>("/errata", {
      method: "POST",
      body,
    });
    return NextResponse.json(data);
  } catch (e) {
    const status = e instanceof ApiError ? e.status : 500;
    return NextResponse.json({ error: "No se pudo enviar el aviso." }, { status });
  }
}
