import { NextResponse } from "next/server";
import { apiFetch, ApiError } from "@/lib/api";

// Proxy POST → /admin/instagram/queue/reorder. Body { ids: number[] } con el
// orden de publicación deseado de los items publicables (pending/prepared).
export async function POST(request: Request) {
  let body: { ids?: unknown };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "body no válido" }, { status: 400 });
  }
  if (!Array.isArray(body.ids) || !body.ids.every((x) => Number.isFinite(x))) {
    return NextResponse.json({ error: "ids no válidos" }, { status: 400 });
  }

  try {
    const data = await apiFetch<unknown>("/admin/instagram/queue/reorder", {
      method: "POST",
      body: { ids: body.ids },
    });
    return NextResponse.json(data);
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: String(e.detail) }, { status: e.status });
    }
    return NextResponse.json({ error: "error interno" }, { status: 500 });
  }
}
