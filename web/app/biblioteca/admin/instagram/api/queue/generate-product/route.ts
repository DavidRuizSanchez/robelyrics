import { NextResponse } from "next/server";
import { apiFetch, ApiError } from "@/lib/api";

// POST → genera las piezas que enseñan la web (con datos reales) y las encola.
export async function POST() {
  try {
    const data = await apiFetch<unknown>(
      "/admin/instagram/queue/generate-product",
      { method: "POST", body: {} },
    );
    return NextResponse.json(data);
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: String(e.detail) }, { status: e.status });
    }
    return NextResponse.json({ error: "error interno" }, { status: 500 });
  }
}
