"use server";

import { redirect } from "next/navigation";
import { apiFetch, ApiError } from "@/lib/api";
import { setAuthCookie } from "@/lib/auth";

type VerifyApi = {
  ok: boolean;
  user_id: number;
  access_token: string | null;
  token_type: string;
};

export type VerifyState =
  | { kind: "pending" }
  | { kind: "ok" }
  | { kind: "error"; message: string };

export async function verifyTokenAction(token: string): Promise<VerifyState> {
  try {
    const res = await apiFetch<VerifyApi>(`/auth/verify-email/${token}`, {
      method: "POST",
      authenticated: false,
    });
    if (res.access_token) {
      await setAuthCookie(res.access_token);
    }
  } catch (err) {
    if (err instanceof ApiError) {
      const detail =
        typeof err.detail === "object" && err.detail && "detail" in err.detail
          ? (err.detail as { detail: string }).detail
          : JSON.stringify(err.detail);
      return { kind: "error", message: detail };
    }
    return { kind: "error", message: "Error inesperado" };
  }
  return { kind: "ok" };
}

export async function goToBibliotecaAction() {
  redirect("/biblioteca");
}
