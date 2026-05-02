"use server";

import { redirect } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { setAuthCookie } from "@/lib/auth";

type LoginResponse = { access_token: string; token_type: string };

export async function loginAction(formData: FormData) {
  const email = String(formData.get("email") || "").trim();
  const password = String(formData.get("password") || "");
  const from = String(formData.get("from") || "/biblioteca");

  if (!email || !password) {
    return { error: "Email y contraseña son obligatorios" };
  }

  try {
    const data = await apiFetch<LoginResponse>("/auth/login", {
      method: "POST",
      body: { email, password },
      authenticated: false,
    });
    await setAuthCookie(data.access_token);
  } catch (err) {
    return { error: "Credenciales inválidas" };
  }

  // Redirige fuera del try/catch (NEXT_REDIRECT lanza un error que no debemos atrapar)
  redirect(from || "/biblioteca");
}
