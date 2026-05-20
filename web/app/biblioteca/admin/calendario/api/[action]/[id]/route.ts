import { NextResponse } from "next/server";
import { apiFetch, ApiError } from "@/lib/api";

const VALID_ACTIONS = new Set(["schedule", "unschedule", "discard"]);

// Proxy POST que delega en /admin/proposals/{id}/{action} con auth via cookie.
// `schedule` lleva body { date: "YYYY-MM-DD" }; el resto no llevan body.
export async function POST(
  request: Request,
  { params }: { params: Promise<{ action: string; id: string }> },
) {
  const { action, id } = await params;
  if (!VALID_ACTIONS.has(action)) {
    return NextResponse.json({ error: "acción no válida" }, { status: 400 });
  }
  const numericId = Number(id);
  if (!Number.isFinite(numericId)) {
    return NextResponse.json({ error: "id no válido" }, { status: 400 });
  }

  let body: unknown = undefined;
  if (action === "schedule") {
    try {
      body = await request.json();
    } catch {
      return NextResponse.json({ error: "falta el cuerpo JSON" }, { status: 400 });
    }
  }

  try {
    const data = await apiFetch<unknown>(
      `/admin/proposals/${numericId}/${action}`,
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
