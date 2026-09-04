import { NextResponse } from "next/server";
import { apiFetch, ApiError } from "@/lib/api";

// GET  → lista de clips con su procedencia.
// POST → pide un clip nuevo { url, start_s, end_s, subtitle }.
export async function GET() {
  try {
    const data = await apiFetch<unknown>("/admin/instagram/clips?limit=100");
    return NextResponse.json(data);
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: String(e.detail) }, { status: e.status });
    }
    return NextResponse.json({ error: "error interno" }, { status: 500 });
  }
}

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "body no válido" }, { status: 400 });
  }
  try {
    const data = await apiFetch<unknown>("/admin/instagram/clips", {
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
