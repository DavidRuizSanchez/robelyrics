"use server";

import { apiFetch, ApiError } from "@/lib/api";

export type SourceCreateResult = {
  ok: true;
  source_id: number;
  referenced_song_ids: number[];
  referenced_song_slugs: string[];
} | { ok: false; error: string };

export type SourceProcessResult = {
  ok: true;
  source_id: number;
  processed_song_slugs: string[];
  log: string[];
} | { ok: false; error: string };

type SourceCreateApi = {
  source_id: number;
  referenced_song_ids: number[];
  referenced_song_slugs: string[];
};

type SourceProcessApi = {
  source_id: number;
  processed_song_slugs: string[];
  log: string[];
};

export async function createSourceAction(formData: FormData): Promise<SourceCreateResult> {
  const mode = String(formData.get("mode") || "text");
  const kind = String(formData.get("kind") || "manual");
  const url = String(formData.get("url") || "").trim();
  const title = String(formData.get("title") || "").trim() || null;
  const author = String(formData.get("author") || "").trim() || null;
  const content = String(formData.get("content") || "").trim() || null;
  const fetch_url = String(formData.get("fetch_url") || "").trim() || null;
  const youtube_url = String(formData.get("youtube_url") || "").trim() || null;

  if (!url) return { ok: false, error: "URL canónica obligatoria" };
  if (mode === "text" && !content) return { ok: false, error: "Pega contenido" };
  if (mode === "url" && !fetch_url && !url) return { ok: false, error: "URL para scrape obligatoria" };
  if (mode === "youtube" && !youtube_url) return { ok: false, error: "URL de YouTube obligatoria" };

  try {
    const res = await apiFetch<SourceCreateApi>("/admin/sources", {
      method: "POST",
      body: { mode, kind, url, title, author, content, fetch_url, youtube_url },
    });
    return {
      ok: true,
      source_id: res.source_id,
      referenced_song_ids: res.referenced_song_ids,
      referenced_song_slugs: res.referenced_song_slugs,
    };
  } catch (err) {
    if (err instanceof ApiError) {
      const detail =
        typeof err.detail === "object" && err.detail && "detail" in err.detail
          ? (err.detail as { detail: string }).detail
          : JSON.stringify(err.detail);
      return { ok: false, error: detail };
    }
    return { ok: false, error: String(err) };
  }
}

export async function processSourceAction(sourceId: number): Promise<SourceProcessResult> {
  try {
    const res = await apiFetch<SourceProcessApi>(`/admin/sources/${sourceId}/process`, {
      method: "POST",
    });
    return {
      ok: true,
      source_id: res.source_id,
      processed_song_slugs: res.processed_song_slugs,
      log: res.log,
    };
  } catch (err) {
    if (err instanceof ApiError) {
      const detail =
        typeof err.detail === "object" && err.detail && "detail" in err.detail
          ? (err.detail as { detail: string }).detail
          : JSON.stringify(err.detail);
      return { ok: false, error: detail };
    }
    return { ok: false, error: String(err) };
  }
}
