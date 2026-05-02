// Helpers de auth: cookie HttpOnly, expiración del JWT.

import { cookies } from "next/headers";
import { TOKEN_COOKIE } from "./api";

const TTL_SECONDS = 60 * 60 * 24 * 30; // 30 días, igual al JWT del backend

export async function setAuthCookie(token: string) {
  (await cookies()).set(TOKEN_COOKIE, token, {
    httpOnly: true,
    sameSite: "lax",
    secure: false, // local; en producción true
    path: "/",
    maxAge: TTL_SECONDS,
  });
}

export async function clearAuthCookie() {
  (await cookies()).delete(TOKEN_COOKIE);
}

export async function hasAuthCookie(): Promise<boolean> {
  return Boolean((await cookies()).get(TOKEN_COOKIE)?.value);
}
