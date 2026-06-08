import { NextResponse } from "next/server";
import { apiFetch, ApiError } from "@/lib/api";

const VALID_ACTIONS = new Set(["approve", "discard"]);

// Proxy POST → /admin/instagram/queue/bulk-{action}. Body: { ids: number[] }.
export async function POST(
  request: Request,
  { params }: { params: Promise<{ action: string }> },
) {
  const { action } = await params;
  if (!VALID_ACTIONS.has(action)) {
    return NextResponse.json({ error: "acción no válida" }, { status: 400 });
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "body no válido" }, { status: 400 });
  }

  try {
    const data = await apiFetch<unknown>(
      `/admin/instagram/queue/bulk-${action}`,
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
