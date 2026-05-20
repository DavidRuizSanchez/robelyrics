import type { MetadataRoute } from "next";
import { apiFetch } from "@/lib/api";

const SITE_URL = process.env.SITE_URL || "https://entreinteriores.com";

type PublicSitemapEntry = {
  url_path: string;
  last_modified: string;
  entity_type: string;
};

// Sitemap basado en seo_content.published. Solo se incluyen URLs cuyo
// artículo SEO está publicado · el resto no existe para crawlers (devuelve
// 404 desde la plantilla pública).

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const now = new Date();

  // URLs estáticas indexables (no van por seo_content.published).
  const urls: MetadataRoute.Sitemap = [
    { url: `${SITE_URL}/`, lastModified: now, changeFrequency: "weekly", priority: 1.0 },
    { url: `${SITE_URL}/discografia`, lastModified: now, changeFrequency: "weekly", priority: 0.9 },
    { url: `${SITE_URL}/temas`, lastModified: now, changeFrequency: "weekly", priority: 0.85 },
    { url: `${SITE_URL}/lugares`, lastModified: now, changeFrequency: "weekly", priority: 0.85 },
    { url: `${SITE_URL}/conceptos`, lastModified: now, changeFrequency: "weekly", priority: 0.8 },
    { url: `${SITE_URL}/blog`, lastModified: now, changeFrequency: "weekly", priority: 0.85 },
    { url: `${SITE_URL}/personas`, lastModified: now, changeFrequency: "weekly", priority: 0.85 },
    { url: `${SITE_URL}/sobre`, lastModified: now, changeFrequency: "yearly", priority: 0.5 },
    { url: `${SITE_URL}/buscar`, lastModified: now, changeFrequency: "monthly", priority: 0.5 },
    { url: `${SITE_URL}/legal/aviso`, lastModified: now, changeFrequency: "yearly", priority: 0.3 },
    { url: `${SITE_URL}/legal/privacidad`, lastModified: now, changeFrequency: "yearly", priority: 0.3 },
    { url: `${SITE_URL}/legal/cookies`, lastModified: now, changeFrequency: "yearly", priority: 0.3 },
    { url: `${SITE_URL}/legal/terminos`, lastModified: now, changeFrequency: "yearly", priority: 0.3 },
    { url: `${SITE_URL}/legal/takedown`, lastModified: now, changeFrequency: "yearly", priority: 0.3 },
    { url: `${SITE_URL}/legal/atribuciones`, lastModified: now, changeFrequency: "yearly", priority: 0.3 },
  ];

  // Detalles de taxonomías y posts publicados.
  try {
    const [themes, places, concepts, posts] = await Promise.all([
      apiFetch<{ slug: string; song_count: number }[]>("/public/themes", { authenticated: false }),
      apiFetch<{ slug: string; song_count: number }[]>("/public/places", { authenticated: false }),
      apiFetch<{ slug: string; song_count: number }[]>("/public/concepts", { authenticated: false }),
      apiFetch<{ slug: string; published_at: string }[]>("/public/posts", { authenticated: false }),
    ]);
    for (const t of themes) {
      urls.push({ url: `${SITE_URL}/temas/${t.slug}`, lastModified: now, changeFrequency: "weekly", priority: 0.7 });
    }
    for (const p of places) {
      urls.push({ url: `${SITE_URL}/lugares/${p.slug}`, lastModified: now, changeFrequency: "weekly", priority: 0.7 });
    }
    for (const c of concepts) {
      urls.push({ url: `${SITE_URL}/conceptos/${c.slug}`, lastModified: now, changeFrequency: "weekly", priority: 0.7 });
    }
    for (const post of posts) {
      urls.push({
        url: `${SITE_URL}/blog/${post.slug}`,
        lastModified: new Date(post.published_at),
        changeFrequency: "monthly",
        priority: 0.65,
      });
    }
  } catch {
    // Si los endpoints fallan, seguimos con las URLs estáticas + sitemap-entries.
  }

  let entries: PublicSitemapEntry[] = [];
  try {
    entries = await apiFetch<PublicSitemapEntry[]>("/public/sitemap-entries", {
      authenticated: false,
    });
  } catch {
    return urls;
  }

  const priorityFor = (kind: string) =>
    kind === "artist"
      ? 0.9
      : kind === "album"
      ? 0.8
      : kind === "person"
      ? 0.75
      : 0.7;

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
