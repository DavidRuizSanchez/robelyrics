import { NextResponse } from "next/server";
import { apiFetch, ApiError } from "@/lib/api";

const VALID_ACTIONS = new Set(["prepare", "publish", "discard"]);

// Proxy POST → /admin/instagram/queue/{id}/{action}. `publish` lleva
// body { dry_run: boolean }; el resto no llevan body.
export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string; action: string }> },
) {
  const { id, action } = await params;
  if (!VALID_ACTIONS.has(action)) {
    return NextResponse.json({ error: "acción no válida" }, { status: 400 });
  }
  const numericId = Number(id);
  if (!Number.isFinite(numericId)) {
    return NextResponse.json({ error: "id no válido" }, { status: 400 });
  }

  let body: unknown = undefined;
  if (action === "publish") {
    try {
      body = await request.json();
    } catch {
      body = { dry_run: false };
    }
  }

  try {
    const data = await apiFetch<unknown>(
      `/admin/instagram/queue/${numericId}/${action}`,
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
