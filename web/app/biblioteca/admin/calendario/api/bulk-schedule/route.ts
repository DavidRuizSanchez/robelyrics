import { NextResponse } from "next/server";
import { apiFetch, ApiError } from "@/lib/api";

// Proxy POST → /admin/proposals/bulk-schedule. Body: { ids: number[] }.
export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "body no válido" }, { status: 400 });
  }
  try {
    const data = await apiFetch<unknown>("/admin/proposals/bulk-schedule", {
      method: "POST",
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
