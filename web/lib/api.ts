// Cliente del API para uso desde Server Components y Server Actions.
// Lee la cookie HttpOnly automáticamente y la añade como Authorization header.
// La URL `API_INTERNAL_URL` apunta a la red docker interna (http://api:8000).

import { cookies } from "next/headers";

const API_BASE = process.env.API_INTERNAL_URL || "http://api:8000";
export const TOKEN_COOKIE = "robelyrics_token";

type FetchOptions = {
  method?: "GET" | "POST" | "PUT" | "DELETE";
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
    let detail: unknown;
    try {
      detail = await res.json();
    } catch {
      detail = await res.text();
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}
