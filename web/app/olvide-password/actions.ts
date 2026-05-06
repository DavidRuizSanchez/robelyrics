"use server";

import { apiFetch } from "@/lib/api";

type ForgotResponse = { ok: boolean };

/**
 * Server action de "olvidé mi contraseña". Llama al backend
 * /auth/forgot-password (rate-limited 3/hour) y SIEMPRE devuelve la
 * misma forma `{ok: true}` exista o no el email — el backend ya
 * uniformiza la respuesta. Esta capa propaga ese contrato sin
 * leakear errores que pudieran filtrar info.
 */
export async function forgotPasswordAction(formData: FormData) {
  const email = String(formData.get("email") || "").trim();
  if (!email) return { error: "Email obligatorio" };
  try {
    await apiFetch<ForgotResponse>("/auth/forgot-password", {
      method: "POST",
      body: { email },
      authenticated: false,
    });
  } catch {
    // Errores del backend (red, validación, rate limit) caen aquí.
    // No mostramos el detalle — respuesta uniforme positiva.
  }
  return { ok: true, email };
}
