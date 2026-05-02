import type { MetadataRoute } from "next";
import { apiFetch } from "@/lib/api";

const SITE_URL = process.env.SITE_URL || "http://localhost:3001";

type PublicSitemapEntry = {
  url_path: string;
  last_modified: string;
  entity_type: string;
};

// Sitemap basado en seo_content.published. Solo se incluyen URLs cuyo
// artículo SEO está publicado — el resto no existe para crawlers (devuelve
// 404 desde la plantilla pública).

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const now = new Date();
  const urls: MetadataRoute.Sitemap = [
    { url: `${SITE_URL}/`, lastModified: now, changeFrequency: "monthly", priority: 1.0 },
  ];

  let entries: PublicSitemapEntry[] = [];
  try {
    entries = await apiFetch<PublicSitemapEntry[]>("/public/sitemap-entries", {
      authenticated: false,
    });
  } catch {
    return urls;
  }

  const priorityFor = (kind: string) =>
    kind === "artist" ? 0.9 : kind === "album" ? 0.8 : 0.7;

  for (const e of entries) {
    urls.push({
      url: `${SITE_URL}${e.url_path}`,
      lastModified: new Date(e.last_modified),
      changeFrequency: "monthly",
      priority: priorityFor(e.entity_type),
    });
  }

  return urls;
}
