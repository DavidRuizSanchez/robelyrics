import { NextResponse } from "next/server";
import { apiFetch, ApiError } from "@/lib/api";

const VALID_ACTIONS = new Set(["publish", "reject", "unpublish"]);

// Proxy POST que delega al endpoint admin del backend con auth via cookie.
export async function POST(
  _request: Request,
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

  try {
    const data = await apiFetch<unknown>(`/admin/posts/${numericId}/${action}`, {
      method: "POST",
    });
    return NextResponse.json(data);
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json(
        { error: String(e.detail) },
        { status: e.status },
      );
    }
    return NextResponse.json({ error: "internal error" }, { status: 500 });
  }
}
