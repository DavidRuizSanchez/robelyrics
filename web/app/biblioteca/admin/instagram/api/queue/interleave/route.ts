import { NextResponse } from "next/server";
import { apiFetch, ApiError } from "@/lib/api";

// Proxy POST → /admin/instagram/queue/interleave (reordena intercalando tipos).
export async function POST() {
  try {
    const data = await apiFetch<unknown>("/admin/instagram/queue/interleave", {
      method: "POST",
    });
    return NextResponse.json(data);
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: String(e.detail) }, { status: e.status });
    }
    return NextResponse.json({ error: "error interno" }, { status: 500 });
  }
}
