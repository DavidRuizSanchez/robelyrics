import { NextResponse } from "next/server";
import { apiFetch, ApiError } from "@/lib/api";

// Proxy admin: resolver una errata (applied|rejected).
export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let body: { action?: string; note?: string | null };
  try {
    body = (await request.json()) as { action?: string; note?: string | null };
  } catch {
    return NextResponse.json({ error: "Datos no válidos." }, { status: 400 });
  }
  try {
    const data = await apiFetch(`/errata/admin/${id}/resolve`, { method: "POST", body });
    return NextResponse.json(data);
  } catch (e) {
    const status = e instanceof ApiError ? e.status : 500;
    return NextResponse.json({ error: "No se pudo resolver." }, { status });
  }
}
