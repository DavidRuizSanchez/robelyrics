import { NextResponse } from "next/server";
import { apiFetch, ApiError } from "@/lib/api";

// Acciones que delegan a POST /admin/posts/{id}/{action}; "update" hace
// PUT /admin/posts/{id}; "schedule"/"update" llevan body JSON.
const VALID_ACTIONS = new Set([
  "publish",
  "reject",
  "unpublish",
  "schedule",
  "unschedule",
  "update",
]);

const WITH_BODY = new Set(["schedule", "update"]);

// Proxy que delega al endpoint admin del backend con auth via cookie.
export async function POST(
  request: Request,
  { params }: { params: Promise<{ action: string; id: string }> },
) {
  const { action, id } = await params;
  if (!VALID_ACTIONS.has(action)) {
    return NextResponse.json({ error: "invalid action" }, { status: 400 });
  }
  const numericId = Number(id);
  if (!Number.isFinite(numericId)) {
    return NextResponse.json({ error: "invalid id" }, { status: 400 });
  }

  let body: unknown = undefined;
  if (WITH_BODY.has(action)) {
    try {
      body = await request.json();
    } catch {
      body = undefined;
    }
  }

  const backendPath =
    action === "update"
      ? `/admin/posts/${numericId}`
      : `/admin/posts/${numericId}/${action}`;
  const method = action === "update" ? "PUT" : "POST";

  try {
    const data = await apiFetch<unknown>(backendPath, { method, body });
    return NextResponse.json(data);
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: String(e.detail) }, { status: e.status });
    }
    return NextResponse.json({ error: "internal error" }, { status: 500 });
  }
}
