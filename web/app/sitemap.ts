import type { MetadataRoute } from "next";
import { apiFetch } from "@/lib/api";

const SITE_URL = process.env.SITE_URL || "http://localhost:3001";

type PublicArtist = { slug: string };
type PublicAlbum = { slug: string };
type PublicArtistDetail = PublicArtist & {
  albums: { slug: string }[];
};
type PublicAlbumDetail = {
  slug: string;
  tracks: { slug: string }[];
};

// El sitemap se genera leyendo la BD vía endpoints públicos. En F.5 se filtrará
// para incluir solo entidades con `seo_content.published = true`. De momento
// incluimos todo el catálogo como hint para crawlers; las páginas que no
// existan devolverán 404 hasta que F.5 cree los templates.

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const now = new Date();
  const urls: MetadataRoute.Sitemap = [
    { url: `${SITE_URL}/`, lastModified: now, changeFrequency: "monthly", priority: 1.0 },
  ];

  let artists: PublicArtist[] = [];
  try {
    artists = await apiFetch<PublicArtist[]>("/public/artists");
  } catch {
    return urls;
  }

  for (const a of artists) {
    urls.push({
      url: `${SITE_URL}/${a.slug}`,
      lastModified: now,
      changeFrequency: "monthly",
      priority: 0.9,
    });

    let detail: PublicArtistDetail;
    try {
      detail = await apiFetch<PublicArtistDetail>(`/public/artists/${a.slug}`);
    } catch {
      continue;
    }

    for (const album of detail.albums) {
      urls.push({
        url: `${SITE_URL}/${a.slug}/${album.slug}`,
        lastModified: now,
        changeFrequency: "monthly",
        priority: 0.8,
      });

      let albumDetail: PublicAlbumDetail;
      try {
        albumDetail = await apiFetch<PublicAlbumDetail>(`/public/albums/${album.slug}`);
      } catch {
        continue;
      }
      for (const track of albumDetail.tracks) {
        urls.push({
          url: `${SITE_URL}/${a.slug}/${album.slug}/${track.slug}`,
          lastModified: now,
          changeFrequency: "monthly",
          priority: 0.7,
        });
      }
    }
  }

  return urls;
}
