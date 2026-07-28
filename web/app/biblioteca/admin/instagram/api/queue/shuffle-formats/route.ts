import { NextResponse } from "next/server";
import { apiFetch, ApiError } from "@/lib/api";

// POST → /admin/instagram/queue/shuffle-formats : reparte formatos variados
// (foto / carrusel / reel) entre los posts, sin tocar los fijados a mano.
export async function POST(request: Request) {
  let body: unknown = {};
  try {
    body = await request.json();
  } catch {
    // Sin body vale: el backend tiene sus valores por defecto.
  }
  try {
    const data = await apiFetch<unknown>(
      "/admin/instagram/queue/shuffle-formats",
      { method: "POST", body },
    );
    return NextResponse.json(data);
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: String(e.detail) }, { status: e.status });
    }
    return NextResponse.json({ error: "error interno" }, { status: 500 });
  }
}
