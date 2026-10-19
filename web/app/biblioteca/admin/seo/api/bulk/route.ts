import { NextResponse } from "next/server";
import { apiFetch, ApiError } from "@/lib/api";

// Proxy admin: publicar o despublicar varias fichas SEO a la vez. Hace lo mismo
// que el botón de cada ficha (marca revisada y publica), en una sola llamada.
const DESTINO = { publish: "/admin/seo/bulk-publish", unpublish: "/admin/seo/bulk-unpublish" } as const;

export async function POST(request: Request) {
  let body: { ids?: unknown; action?: unknown };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Datos no válidos." }, { status: 400 });
  }
  const ids = Array.isArray(body.ids) ? body.ids.filter((x): x is number => Number.isInteger(x)) : [];
  const action = body.action === "publish" || body.action === "unpublish" ? body.action : null;
  if (!action || ids.length === 0) {
    return NextResponse.json({ error: "Falta la acción o la selección." }, { status: 400 });
  }
  try {
    const data = await apiFetch(DESTINO[action], { method: "POST", body: { ids } });
    return NextResponse.json(data);
  } catch (e) {
    const status = e instanceof ApiError ? e.status : 500;
    return NextResponse.json({ error: "No se pudo completar la operación." }, { status });
  }
}
