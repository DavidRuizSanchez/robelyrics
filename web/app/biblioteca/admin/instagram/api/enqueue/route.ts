import { NextResponse } from "next/server";
import { apiFetch, ApiError } from "@/lib/api";

// Proxy POST → /admin/instagram/enqueue. Body: { news_item_id } o { blog_post_id }.
export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "falta el cuerpo JSON" }, { status: 400 });
  }
  try {
    const data = await apiFetch<unknown>("/admin/instagram/enqueue", {
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
