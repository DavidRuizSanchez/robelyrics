"use server";

import { redirect } from "next/navigation";
import { ApiError, apiFetch } from "@/lib/api";
import { setAuthCookie } from "@/lib/auth";

type ResetResponse = { ok: boolean; access_token: string };

/**
 * Consume el token de reset y cambia la contraseña. Tras éxito el backend
 * marca tokens_invalid_before en el user, lo que cierra todas las sesiones
 * activas (otros dispositivos). Aquí obtenemos un access_token nuevo
 * para auto-login en el dispositivo actual.
 */
export async function resetPasswordAction(formData: FormData) {
  const token = String(formData.get("token") || "").trim();
  const password = String(formData.get("password") || "");
  const confirm = String(formData.get("confirm") || "");

  if (!token) return { error: "Token no válido" };
  if (password.length < 8) {
    return { error: "Contraseña insegura · mínimo 8 caracteres con letras y números" };
  }
  if (!/[A-Za-z]/.test(password) || !/\d/.test(password)) {
    return { error: "La contraseña debe incluir letras y números" };
  }
  if (password !== confirm) {
    return { error: "Las contraseñas no coinciden" };
  }

  let data: ResetResponse;
  try {
    data = await apiFetch<ResetResponse>(`/auth/reset-password/${encodeURIComponent(token)}`, {
      method: "POST",
      body: { password },
      authenticated: false,
    });
  } catch (err) {
    if (err instanceof ApiError) {
      const detail =
        typeof err.detail === "object" && err.detail && "detail" in err.detail
          ? String((err.detail as { detail?: unknown }).detail)
          : "Token inválido o caducado";
      return { error: detail };
    }
    return { error: "Error al restablecer contraseña" };
  }

  await setAuthCookie(data.access_token);
  redirect("/biblioteca");
}
