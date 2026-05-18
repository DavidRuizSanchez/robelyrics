import Link from "next/link";
import { notFound, permanentRedirect } from "next/navigation";
import AlbumCover from "@/components/AlbumCover";
import Breadcrumbs from "@/components/Breadcrumbs";
import HeaderImageBackdrop from "@/components/HeaderImageBackdrop";
import MarkdownArticle from "@/components/MarkdownArticle";
import PublicFooter from "@/components/PublicFooter";
import PublicHeader from "@/components/PublicHeader";
import RelatedSongs from "@/components/RelatedSongs";
import TaxonomyPills from "@/components/TaxonomyPills";
import TrackNav from "@/components/TrackNav";
import { apiFetch, ApiError } from "@/lib/api";
import { safeJsonLd } from "@/lib/safe-json-ld";
import { resolveSlug } from "@/lib/slug-resolver";
import type { PublicAlbumDetail, PublicSongDetail } from "@/lib/types";

async function tryResolveSong(
  albumSlug: string,
  pedido: string,
): Promise<string | null> {
  try {
    const album = await apiFetch<PublicAlbumDetail>(
      `/public/albums/${albumSlug}`,
      { authenticated: false },
    );
    return resolveSlug(
      pedido,
      album.tracks.map((t) => t.slug),
    );
  } catch {
    return null;
  }
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ artist: string; album: string; song: string }>;
}) {
  const { song } = await params;
  try {
    const detail = await apiFetch<PublicSongDetail>(`/public/songs/${song}`, {
      authenticated: false,
    });
    if (!detail.seo_body) return {};
    return {
      title:
        detail.seo_meta_title ||
        `${detail.title} · ${detail.album.title} · ${detail.artist.name}`,
      description: detail.seo_meta_description || "",
      openGraph: {
        title: detail.seo_meta_title || detail.title,
        description: detail.seo_meta_description || "",
        images: detail.album.cover_url ? [detail.album.cover_url] : [],
        type: "article",
      },
    };
  } catch {
    return {};
  }
}

export default async function SongPublicPage({
  params,
}: {
  params: Promise<{ artist: string; album: string; song: string }>;
}) {
  const { artist, album, song } = await params;
  let detail: PublicSongDetail;
  try {
    detail = await apiFetch<PublicSongDetail>(`/public/songs/${song}`, {
      authenticated: false,
    });
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) {
      const matched = await tryResolveSong(album, song);
      if (matched) permanentRedirect(`/${artist}/${album}/${matched}`);
      notFound();
    }
    throw e;
  }
  if (!detail.seo_body) notFound();

  // Pillamos el tracklist del álbum para los bloques prev/next + "más del
  // álbum". Si falla (raro), simplemente no renderizamos esos bloques.
  let albumDetail: PublicAlbumDetail | null = null;
  try {
    albumDetail = await apiFetch<PublicAlbumDetail>(
      `/public/albums/${album}`,
      { authenticated: false },
    );
  } catch {
    albumDetail = null;
  }

  // Backdrop: la canción puede tener su propia carátula (single, EP, clip).
  // Si no, caemos a la del álbum. Algunas no tienen ninguna → sin backdrop.
  const backdropSrc = detail.cover_url || detail.album.cover_url || null;

  return (
    <div className="relative">
      {backdropSrc && (
        <HeaderImageBackdrop
          src={backdropSrc}
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
            { label: detail.artist.name, href: `/${artist}` },
            {
              label: detail.album.title,
              href: `/${artist}/${album}`,
              meta: `(${detail.album.year})`,
            },
            { label: detail.title, href: `/${artist}/${album}/${song}` },
          ]}
        />

        <header className="mb-10 grid grid-cols-1 md:grid-cols-[180px_1fr] gap-6 md:gap-8 items-start">
          <AlbumCover
            coverUrl={detail.album.cover_url}
            slug={detail.album.slug}
            title={detail.album.title}
            variant="md"
            className="!w-full !h-auto aspect-square"
          />
          <div>
            {detail.track_number != null && (
              <p className="font-mono text-[11px] tracking-[3px] uppercase text-accent">
                — {String(detail.track_number).padStart(2, "0")}
              </p>
            )}
            <h1 className="font-serif text-4xl md:text-[58px] text-ink leading-[0.97] tracking-[-1px] mt-2 mb-4">
              {detail.seo_h1 || detail.title}
            </h1>
            {detail.youtube_id && (
              <p className="font-mono text-[10px] tracking-[2px] uppercase text-ink-dim">
                <a
                  href={`https://www.youtube.com/watch?v=${detail.youtube_id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  data-cursor="hover"
                  className="text-accent hover:underline"
                >
                  ▶ escuchar en YouTube
                </a>
              </p>
            )}
          </div>
        </header>

        {detail.youtube_id && (
          <div className="aspect-video w-full max-w-[720px] mb-12 bg-black overflow-hidden">
            <iframe
              src={`https://www.youtube.com/embed/${detail.youtube_id}?rel=0&modestbranding=1`}
              title={detail.title}
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
              allowFullScreen
              className="w-full h-full"
            />
          </div>
        )}

        <article className="mb-12">
          <MarkdownArticle markdown={detail.seo_body} />
        </article>

        {detail.snippet.length > 0 && (
          <section className="mt-16 max-w-[680px] border-l-2 border-accent/40 pl-6 py-2">
            <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-3">
              Fragmento citado
            </p>
            <div className="font-serif italic text-[20px] md:text-[22px] text-ink leading-[1.6] space-y-1">
              {detail.snippet.map((line, i) => (
                <p key={i}>{line}</p>
              ))}
            </div>
            <p className="mt-4 font-mono text-[10px] tracking-[2px] uppercase text-ink-faint leading-relaxed">
              {detail.snippet_attribution}.{" "}
              {detail.genius_url && (
                <a
                  href={detail.genius_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  data-cursor="hover"
                  className="text-accent hover:underline"
                >
                  Ver letra completa en Genius →
                </a>
              )}
            </p>
          </section>
        )}

        <TaxonomyPills
          themes={detail.themes}
          places={detail.places}
          concepts={detail.concepts}
        />

        {albumDetail && (
          <>
            <TrackNav
              artistSlug={artist}
              albumSlug={album}
              currentSlug={song}
              tracks={albumDetail.tracks}
            />
            <RelatedSongs
              artistSlug={artist}
              albumSlug={album}
              albumTitle={detail.album.title}
              currentSlug={song}
              tracks={albumDetail.tracks}
            />
          </>
        )}

        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: safeJsonLd({
              "@context": "https://schema.org",
              "@type": "MusicComposition",
              name: detail.title,
              composer: { "@type": "MusicGroup", name: detail.artist.name },
              inAlbum: {
                "@type": "MusicAlbum",
                name: detail.album.title,
                datePublished: String(detail.album.year),
              },
              url: `/${artist}/${album}/${song}`,
            }),
          }}
        />
      </main>
      <PublicFooter />
      </div>
    </div>
  );
}
