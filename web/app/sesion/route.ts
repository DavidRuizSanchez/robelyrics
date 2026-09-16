import { NextResponse } from "next/server";
import { apiFetch } from "@/lib/api";
import type { AuthMe } from "@/lib/types";

// Estado de sesión para las páginas públicas, que se sirven cacheadas (ISR) y
// por eso no pueden leer la cookie al renderizar: el HTML es el mismo para
// todos. La cabecera y la home lo piden desde el cliente (`ForSession`).
//
// Vive fuera de /api (Caddy manda /api/* al FastAPI) y de /biblioteca (el
// middleware redirige a /login sin token).

export const dynamic = "force-dynamic";

const PRIVADO = {
  "Cache-Control": "private, no-store",
  "X-Robots-Tag": "noindex, nofollow",
};

export async function GET() {
  let me: AuthMe | null = null;
  try {
    me = await apiFetch<AuthMe>("/auth/me");
  } catch {
    me = null;
  }
  return NextResponse.json(
    { logged_in: Boolean(me), is_admin: Boolean(me?.is_admin) },
    { headers: PRIVADO },
  );
}
