import Link from "next/link";
import { notFound, permanentRedirect } from "next/navigation";
import AlbumCover from "@/components/AlbumCover";
import AlbumDataTable from "@/components/AlbumDataTable";
import Breadcrumbs from "@/components/Breadcrumbs";
import HeaderImageBackdrop from "@/components/HeaderImageBackdrop";
import MarkdownArticle from "@/components/MarkdownArticle";
import RelatedPosts from "@/components/RelatedPosts";
import MoreFromArtist from "@/components/MoreFromArtist";
import PublicFooter from "@/components/PublicFooter";
import PublicHeader from "@/components/PublicHeader";
import { apiFetch, redirectTargetOf } from "@/lib/api";
import { safeJsonLd } from "@/lib/safe-json-ld";
import { SITE_URL } from "@/lib/site";
import {
  breadcrumbListNode,
  buildGraph,
  canonical,
  mentionsArray,
  musicAlbumNode,
  musicGroupNode,
  webPageNode,
} from "@/lib/schema-graph";
import type { PublicAlbumDetail, PublicArtistDetail } from "@/lib/types";

/**
 * El artista viaja a la API: `albums.slug` solo es único dentro del artista, así
 * que pedirlo suelto hacía que `/robe/la-ley-innata` (disco de Extremoduro)
 * devolviera 200 con la ficha buena colgando de un artista que no es.
 */
function albumPath(artist: string, album: string): string {
  return `/public/albums/${artist}/${album}`;
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ artist: string; album: string }>;
}) {
  const { artist, album } = await params;
  try {
    const detail = await apiFetch<PublicAlbumDetail>(albumPath(artist, album), {
      authenticated: false,
    });
    if (!detail.seo_body) return {};
    return {
      title: detail.seo_meta_title || `${detail.title} · ${detail.artist.name}`,
      description: detail.seo_meta_description || "",
      alternates: { canonical: `${SITE_URL}${detail.canonical_path}` },
      openGraph: {
        title: detail.seo_meta_title || detail.title,
        description: detail.seo_meta_description || "",
        images: detail.cover_url ? [detail.cover_url] : [],
      },
    };
  } catch {
    return {};
  }
}

export default async function AlbumPublicPage({
  params,
}: {
  params: Promise<{ artist: string; album: string }>;
}) {
  const { artist, album } = await params;
  let detail: PublicAlbumDetail;
  try {
    detail = await apiFetch<PublicAlbumDetail>(albumPath(artist, album), {
      authenticated: false,
    });
  } catch (e) {
    const destino = redirectTargetOf(e);
    if (destino) permanentRedirect(destino);
    notFound();
  }
  if (!detail.seo_body) notFound();

  // Segundo cerrojo: la ruta servida tiene que ser la canónica. Ver la página
  // de canción, donde este mismo descuido servía el disco equivocado con un 200.
  if (detail.canonical_path !== `/${artist}/${album}`) {
    permanentRedirect(detail.canonical_path);
  }

  // De aquí en adelante todo sale de `detail`, no de `params`.
  const artistSlug = detail.artist.slug;
  const albumSlug = detail.slug;

  // Cargamos el artista para los álbumes hermanos (bloque "Más discos de…").
  // Si falla, simplemente no renderizamos el bloque.
  let artistDetail: PublicArtistDetail | null = null;
  try {
    artistDetail = await apiFetch<PublicArtistDetail>(
      `/public/artists/${artistSlug}`,
      { authenticated: false },
    );
  } catch {
    artistDetail = null;
  }

  return (
    <div className="relative">
      {detail.cover_url && (
        <HeaderImageBackdrop
          src={detail.cover_url}
          height="900px"
          opacity={0.5}
          position="center top"
          blur={1}
        />
      )}
      <div className="relative z-10">
      <PublicHeader />
      <main className="px-5 md:px-14 py-10 md:py-14 max-w-[1100px] mx-auto">
        <Breadcrumbs
          className="mb-6"
          items={[
            { label: "Entre Interiores", href: "/" },
            { label: detail.artist.name, href: `/${artistSlug}` },
            {
              label: detail.title,
              href: `/${artistSlug}/${albumSlug}`,
              meta: `(${detail.year})`,
            },
          ]}
        />

        <header className="mt-6 mb-12 grid grid-cols-1 md:grid-cols-[260px_1fr] gap-8 md:gap-10 items-start">
          <AlbumCover
            coverUrl={detail.cover_url}
            slug={detail.slug}
            title={detail.title}
            variant="lg"
            className="!w-full !h-auto aspect-square"
          />
          <div>
            <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent">
              {detail.year} · {detail.kind}
            </p>
            <h1 className="font-serif text-4xl md:text-[64px] text-ink leading-[0.95] tracking-[-1px] mt-2 mb-4">
              {detail.seo_h1 || detail.title}
            </h1>
          </div>
        </header>

        <article className="mb-4">
          <MarkdownArticle markdown={detail.seo_body} />
        </article>

        <AlbumDataTable detail={detail} />

        <section className="mt-12">
          <h2 className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-5">
            Canciones
          </h2>
          <ol className="space-y-1">
            {detail.tracks.map((t, i) => (
              <li key={t.slug}>
                <Link
                  href={`/${artistSlug}/${albumSlug}/${t.slug}`}
                  data-cursor="hover"
                  className="group flex items-baseline gap-4 py-3 px-4 -mx-4 hover:bg-paper transition-colors"
                >
                  <span className="font-mono text-[11px] text-ink-faint tabular-nums w-8 text-right">
                    {t.track_number ?? i + 1}
                  </span>
                  <span className="font-serif text-[18px] md:text-[20px] flex-1 text-ink group-hover:text-accent transition-colors">
                    {t.title}
                  </span>
                </Link>
              </li>
            ))}
          </ol>
        </section>

        {artistDetail && (
          <MoreFromArtist
            artistSlug={artistSlug}
            artistName={detail.artist.name}
            albums={artistDetail.albums}
            currentAlbumSlug={albumSlug}
          />
        )}

        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: safeJsonLd(
              buildGraph([
                {
                  ...musicAlbumNode({
                    slug: albumSlug,
                    artistSlug: artistSlug,
                    title: detail.title,
                    year: detail.year,
                    coverUrl: detail.cover_url,
                    tracks: detail.tracks.map((t) => ({
                      slug: t.slug,
                      title: t.title,
                    })),
                  }),
                  ...(mentionsArray(detail.entities).length > 0
                    ? { mentions: mentionsArray(detail.entities) }
                    : {}),
                },
                // Nodo mínimo del artista para conectar @id
                musicGroupNode({ slug: artistSlug, name: detail.artist.name }),
                webPageNode({
                  path: `/${artistSlug}/${albumSlug}`,
                  name: detail.title,
                  type: "ItemPage",
                  description: detail.seo_meta_description,
                  mainEntityId: canonical.musicAlbum(artistSlug, albumSlug),
                }),
                breadcrumbListNode(`/${artistSlug}/${albumSlug}`, [
                  { name: "Entre Interiores", item: "/" },
                  { name: detail.artist.name, item: `/${artistSlug}` },
                  { name: detail.title, item: `/${artistSlug}/${albumSlug}` },
                ]),
              ]),
            ),
          }}
        />

        <RelatedPosts entityType="album" slug={albumSlug} />
      </main>
      <PublicFooter />
      </div>
    </div>
  );
}
