"use server";

import { revalidatePath } from "next/cache";
import { apiFetch, ApiError } from "@/lib/api";

export type SeoActionResult =
  | { ok: true; published: boolean; reviewed: boolean }
  | { ok: false; error: string };

export async function updateSeoAction(
  id: number,
  formData: FormData,
): Promise<SeoActionResult> {
  const body_md = String(formData.get("body_md") || "").trim();
  const meta_title = String(formData.get("meta_title") || "").trim() || null;
  const meta_description = String(formData.get("meta_description") || "").trim() || null;
  if (body_md.length < 100) {
    return { ok: false, error: "El cuerpo es demasiado corto" };
  }
  try {
    await apiFetch(`/admin/seo/${id}`, {
      method: "PUT",
      body: { body_md, meta_title, meta_description },
    });
  } catch (err) {
    return errorOf(err);
  }
  revalidatePath(`/biblioteca/admin/seo/${id}`);
  revalidatePath("/biblioteca/admin/seo");
  return { ok: true, published: false, reviewed: true };
}

export async function publishSeoAction(id: number): Promise<SeoActionResult> {
  try {
    await apiFetch(`/admin/seo/${id}/publish`, { method: "POST" });
  } catch (err) {
    return errorOf(err);
  }
  revalidatePath(`/biblioteca/admin/seo/${id}`);
  revalidatePath("/biblioteca/admin/seo");
  return { ok: true, published: true, reviewed: true };
}

export async function unpublishSeoAction(id: number): Promise<SeoActionResult> {
  try {
    await apiFetch(`/admin/seo/${id}/unpublish`, { method: "POST" });
  } catch (err) {
    return errorOf(err);
  }
  revalidatePath(`/biblioteca/admin/seo/${id}`);
  revalidatePath("/biblioteca/admin/seo");
  return { ok: true, published: false, reviewed: true };
}

function errorOf(err: unknown): { ok: false; error: string } {
  if (err instanceof ApiError) {
    const detail =
      typeof err.detail === "object" && err.detail && "detail" in err.detail
        ? (err.detail as { detail: string }).detail
        : JSON.stringify(err.detail);
    return { ok: false, error: detail };
  }
  return { ok: false, error: String(err) };
}
