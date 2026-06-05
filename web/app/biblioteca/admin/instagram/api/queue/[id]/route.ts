import { NextResponse } from "next/server";
import { apiFetch, ApiError } from "@/lib/api";

// GET → /admin/instagram/queue/{id} : detalle (caption + imagen en base64).
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const numericId = Number(id);
  if (!Number.isFinite(numericId)) {
    return NextResponse.json({ error: "id no válido" }, { status: 400 });
  }
  try {
    const data = await apiFetch<unknown>(`/admin/instagram/queue/${numericId}`);
    return NextResponse.json(data);
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: String(e.detail) }, { status: e.status });
    }
    return NextResponse.json({ error: "error interno" }, { status: 500 });
  }
}

// PATCH → /admin/instagram/queue/{id} : edita caption/título/resumen a mano.
export async function PATCH(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const numericId = Number(id);
  if (!Number.isFinite(numericId)) {
    return NextResponse.json({ error: "id no válido" }, { status: 400 });
  }
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "body no válido" }, { status: 400 });
  }
  try {
    const data = await apiFetch<unknown>(`/admin/instagram/queue/${numericId}`, {
      method: "PATCH",
      body,
    });
    return NextResponse.json(data);
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: String(e.detail) }, { status: e.status });
    }
    return NextResponse.json({ error: "error interno" }, { status: 500 });
  }
}
