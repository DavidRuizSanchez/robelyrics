// Cliente del API para uso desde Server Components y Server Actions.
// Lee la cookie HttpOnly automáticamente y la añade como Authorization header.
// La URL `API_INTERNAL_URL` apunta a la red docker interna (http://api:8000).

import { cookies } from "next/headers";

const API_BASE = process.env.API_INTERNAL_URL || "http://api:8000";
export const TOKEN_COOKIE = "robelyrics_token";

type FetchOptions = {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  cache?: RequestCache;
  // Si false, no envía Authorization (para /auth/login)
  authenticated?: boolean;
};

export class ApiError extends Error {
  constructor(public status: number, public detail: unknown) {
    super(`API ${status}: ${JSON.stringify(detail)}`);
  }
}

/**
 * Ruta canónica que propone la API cuando una URL de catálogo no casa.
 *
 * Los endpoints de canción y disco responden 404 con `redirect_to` cuando la
 * ruta apunta a una entidad real pero por el sitio equivocado (el disco de otro
 * artista, o una canción colgando de un disco que no es el suyo). Devuelve null
 * si el 404 es un 404 de verdad.
 *
 * FastAPI envuelve el detalle en `{detail: ...}`, así que hay que bajar dos
 * niveles: `body.detail.redirect_to`.
 */
export function redirectTargetOf(e: unknown): string | null {
  if (!(e instanceof ApiError) || e.status !== 404) return null;
  const body = e.detail as { detail?: { redirect_to?: unknown } } | null;
  const destino = body?.detail?.redirect_to;
  return typeof destino === "string" && destino.startsWith("/") ? destino : null;
}

export async function apiFetch<T>(path: string, opts: FetchOptions = {}): Promise<T> {
  const { method = "GET", body, cache = "no-store", authenticated = true } = opts;
  const headers: Record<string, string> = { "Content-Type": "application/json" };

  if (authenticated) {
    const token = (await cookies()).get(TOKEN_COOKIE)?.value;
    if (token) headers.Authorization = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    cache,
  });

  if (!res.ok) {
    // Leer body una sola vez como texto y intentar parsear como JSON.
    // Antes hacía res.json() y caía a res.text() en el catch, pero el body
    // de fetch solo se puede consumir una vez → "Body has already been read".
    const text = await res.text();
    let detail: unknown = text;
    try {
      detail = JSON.parse(text);
    } catch {
      // queda como text
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}
