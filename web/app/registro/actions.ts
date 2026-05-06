"use server";

import { apiFetch, ApiError } from "@/lib/api";

export type RegisterResult =
  | { ok: true; email: string; emailSent: boolean }
  | { ok: false; error: string };

type RegisterApi = {
  user_id: number;
  email_sent: boolean;
};

// La versión de términos debe coincidir con TERMS_VERSION del backend.
// Si en el futuro se cambian los términos, actualizar también esta constante.
const TERMS_VERSION = "2026-05-02";

export async function registerAction(formData: FormData): Promise<RegisterResult> {
  const email = String(formData.get("email") || "").trim().toLowerCase();
  const password = String(formData.get("password") || "");
  const passwordConfirm = String(formData.get("password_confirm") || "");
  const acceptTerms = formData.get("accept_terms") === "on";

  if (!email || !password) return { ok: false, error: "Email y contraseña son obligatorios" };
  if (password.length < 8) return { ok: false, error: "Contraseña: mínimo 8 caracteres" };
  if (!/[A-Za-z]/.test(password) || !/\d/.test(password))
    return { ok: false, error: "Contraseña: incluye al menos una letra y un número" };
  if (password !== passwordConfirm)
    return { ok: false, error: "Las contraseñas no coinciden" };
  if (!acceptTerms)
    return { ok: false, error: "Debes aceptar los términos de uso" };

  try {
    const res = await apiFetch<RegisterApi>("/auth/register", {
      method: "POST",
      body: { email, password, accept_terms_version: TERMS_VERSION },
      authenticated: false,
    });
    return { ok: true, email, emailSent: res.email_sent };
  } catch (err) {
    if (err instanceof ApiError) {
      const detail =
        typeof err.detail === "object" && err.detail && "detail" in err.detail
          ? (err.detail as { detail: string }).detail
          : JSON.stringify(err.detail);
      return { ok: false, error: detail };
    }
    return { ok: false, error: "Error inesperado · inténtalo más tarde" };
  }
}
