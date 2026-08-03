import Link from "next/link";
import { notFound, permanentRedirect } from "next/navigation";
import AlbumCover from "@/components/AlbumCover";
import Breadcrumbs from "@/components/Breadcrumbs";
import HeaderImageBackdrop from "@/components/HeaderImageBackdrop";
import MarkdownArticle from "@/components/MarkdownArticle";
import RelatedPosts from "@/components/RelatedPosts";
import PublicFooter from "@/components/PublicFooter";
import PublicHeader from "@/components/PublicHeader";
import AlbumSiblingSongs from "@/components/AlbumSiblingSongs";
import RelatedSongs from "@/components/RelatedSongs";
import SongDataTable from "@/components/SongDataTable";
import TaxonomyPills from "@/components/TaxonomyPills";
import TrackNav from "@/components/TrackNav";
import { apiFetch, redirectTargetOf } from "@/lib/api";
import { safeJsonLd } from "@/lib/safe-json-ld";
import { SITE_URL } from "@/lib/site";
import {
  breadcrumbListNode,
  buildGraph,
  canonical,
  mentionsArray,
  musicAlbumNode,
  musicCompositionNode,
  musicGroupNode,
  videoObjectNode,
  webPageNode,
} from "@/lib/schema-graph";
import type { PublicAlbumDetail, PublicSongDetail } from "@/lib/types";

/**
 * Los tres segmentos viajan a la API, que resuelve la canción DENTRO de su
 * disco. Antes se pedía `/public/songs/${song}` a secas y el disco se sacaba
 * del segmento de la URL: `/extremoduro/pedra/ama-...-en-directo` devolvía 200
 * con el artículo de una canción y el tracklist, el prev/next y el JSON-LD de
 * otro disco. Cualquier combinación de artista y disco colaba.
 */
function songPath(artist: string, album: string, song: string): string {
  return `/public/songs/${artist}/${album}/${song}`;
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ artist: string; album: string; song: string }>;
}) {
  const { artist, album, song } = await params;
  try {
    const detail = await apiFetch<PublicSongDetail>(
      songPath(artist, album, song),
      { authenticated: false },
    );
    if (!detail.seo_body) return {};
    return {
      title:
        detail.seo_meta_title ||
        `${detail.title} · ${detail.album.title} · ${detail.artist.name}`,
      description: detail.seo_meta_description || "",
      // La canónica sale de la BD, nunca de la URL pedida: si no, cada variante
      // cruzada se declaraba canónica de sí misma y el duplicado era infinito.
      alternates: { canonical: `${SITE_URL}${detail.canonical_path}` },
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
    detail = await apiFetch<PublicSongDetail>(
      songPath(artist, album, song),
      { authenticated: false },
    );
  } catch (e) {
    // La API ya intentó resolverla (typo del slug, disco equivocado, artista
    // equivocado). Si tiene destino, se manda allí; si no, es un 404 de verdad.
    const destino = redirectTargetOf(e);
    if (destino) permanentRedirect(destino);
    notFound();
  }
  if (!detail.seo_body) notFound();

  // Segundo cerrojo, independiente del primero: si la ruta servida no es la
  // canónica, se redirige. Para servir un Frankenstein tendrían que fallar los
  // dos a la vez.
  if (detail.canonical_path !== `/${artist}/${album}/${song}`) {
    permanentRedirect(detail.canonical_path);
  }

  // A partir de aquí NO se vuelve a usar `params`: todo sale de `detail`, que
  // es la BD. Mezclar ambas fuentes fue justo la causa del contenido cruzado.
  const artistSlug = detail.artist.slug;
  const albumSlug = detail.album.slug;
  const songSlug = detail.slug;

  // Pillamos el tracklist del álbum para los bloques prev/next + "más del
  // álbum". Si falla (raro), simplemente no renderizamos esos bloques.
  let albumDetail: PublicAlbumDetail | null = null;
  try {
    albumDetail = await apiFetch<PublicAlbumDetail>(
      `/public/albums/${artistSlug}/${albumSlug}`,
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
            { label: detail.artist.name, href: `/${artistSlug}` },
            {
              label: detail.album.title,
              href: `/${artistSlug}/${albumSlug}`,
              meta: `(${detail.album.year})`,
            },
            { label: detail.title, href: `/${artistSlug}/${albumSlug}/${songSlug}` },
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
                · {String(detail.track_number).padStart(2, "0")}
              </p>
            )}
            <h1 className="font-serif text-4xl md:text-[58px] text-ink leading-[0.97] tracking-[-1px] mt-2 mb-4">
              {detail.seo_h1 || detail.title}
            </h1>
            {detail.credits && detail.credits.length > 0 && (
              <p className="font-mono text-[10px] md:text-[11px] tracking-[2px] uppercase text-ink-dim mb-3 leading-relaxed">
                {detail.credits.map((c, i) => (
                  <span key={`${c.role}-${c.name}`}>
                    {i > 0 && <span className="text-ink-faint"> · </span>}
                    <span className="text-ink-faint">{c.role_label}: </span>
                    {c.person_slug ? (
                      <a
                        href={`/personas/${c.person_slug}`}
                        data-cursor="hover"
                        className="text-accent hover:underline"
                      >
                        {c.name}
                      </a>
                    ) : (
                      <span className="text-ink">{c.name}</span>
                    )}
                  </span>
                ))}
              </p>
            )}
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

        {/* Anterior/siguiente justo debajo del reproductor. */}
        {albumDetail && (
          <TrackNav
            artistSlug={artistSlug}
            albumSlug={albumSlug}
            currentSlug={songSlug}
            tracks={albumDetail.tracks}
          />
        )}

        <SongDataTable detail={detail} />

        <article className="mb-12">
          <MarkdownArticle markdown={detail.seo_body} />
        </article>

        <RelatedSongs songs={detail.related_songs} />

        {/*
          La letra: el fragmento citado al amparo del art. 32 LPI, con un H2 que
          nombra la intención con la que se busca («letra de X»). Antes esto era
          un `<p>` que decía «Fragmento citado» — descriptivo pero mudo: la
          página no declaraba en ningún sitio que aquí se habla de la letra, y
          las queries de esa intención se las llevaban otras páginas.

          La letra COMPLETA no se publica en abierto a propósito; vive en la
          biblioteca, tras registro. El enlace va `nofollow` porque
          `/biblioteca/` está en Disallow del robots.txt (web/app/robots.ts):
          no tiene sentido derramar señal hacia una URL que Google no rastrea.
          Esto no hace rankear para «X letra» —con la caja de letras de Google y
          Genius delante no es ganable—; convierte impresiones en visitas y
          visitas en registros, que es lo que sí está en nuestra mano.
        */}
        {detail.snippet.length > 0 && (
          <section className="mt-16 max-w-[680px] border-l-2 border-accent/40 pl-6 py-2">
            <h2 className="font-serif text-2xl md:text-[28px] text-ink mb-4 leading-[1.2] tracking-[-0.3px]">
              Letra de «{detail.title}»
            </h2>
            <div className="font-serif italic text-[20px] md:text-[22px] text-ink leading-[1.6] space-y-1">
              {detail.snippet.map((line, i) => (
                <p key={i}>{line}</p>
              ))}
            </div>
            <p className="mt-5 font-serif text-[17px] md:text-[18px] text-ink-faint leading-[1.6]">
              La letra completa de «{detail.title}», verso a verso, está en{" "}
              <Link
                href={`/biblioteca/${detail.artist.slug}/${detail.album.slug}/${detail.slug}`}
                rel="nofollow"
                data-cursor="hover"
                className="text-accent hover:underline"
              >
                la biblioteca
              </Link>
              , la zona de lectura del sitio. Hay que registrarse para entrar.
            </p>
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
          <AlbumSiblingSongs
            artistSlug={artistSlug}
            albumSlug={albumSlug}
            albumTitle={detail.album.title}
            currentSlug={songSlug}
            tracks={albumDetail.tracks}
          />
        )}

        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: safeJsonLd(
              buildGraph([
                {
                  ...musicCompositionNode({
                    slug: songSlug,
                    artistSlug: artistSlug,
                    albumSlug: albumSlug,
                    albumTitle: detail.album.title,
                    albumYear: detail.album.year,
                    artistName: detail.artist.name,
                    title: detail.title,
                    credits: detail.credits,
                  }),
                  ...(mentionsArray(detail.entities).length > 0
                    ? { mentions: mentionsArray(detail.entities) }
                    : {}),
                },
                // Nodos mínimos para que Google una entidades cross-page
                musicAlbumNode({
                  slug: albumSlug,
                  artistSlug: artistSlug,
                  title: detail.album.title,
                  year: detail.album.year,
                }),
                musicGroupNode({ slug: artistSlug, name: detail.artist.name }),
                // VideoObject si la canción tiene vídeo de YouTube embebido.
                ...(detail.youtube_id
                  ? [
                      videoObjectNode({
                        artistSlug: artistSlug,
                        albumSlug: albumSlug,
                        songSlug: songSlug,
                        songTitle: detail.title,
                        artistName: detail.artist.name,
                        youtubeId: detail.youtube_id,
                        videoTitle: detail.youtube_title,
                        uploadDate: detail.youtube_published_at,
                        durationSec: detail.youtube_duration_sec,
                      }),
                    ]
                  : []),
                webPageNode({
                  path: `/${artistSlug}/${albumSlug}/${songSlug}`,
                  name: detail.title,
                  type: "ItemPage",
                  description: detail.seo_meta_description,
                  mainEntityId: canonical.musicComposition(artistSlug, albumSlug, songSlug),
                }),
                breadcrumbListNode(`/${artistSlug}/${albumSlug}/${songSlug}`, [
                  { name: "Entre Interiores", item: "/" },
                  { name: detail.artist.name, item: `/${artistSlug}` },
                  { name: detail.album.title, item: `/${artistSlug}/${albumSlug}` },
                  { name: detail.title, item: `/${artistSlug}/${albumSlug}/${songSlug}` },
                ]),
              ]),
            ),
          }}
        />

        <RelatedPosts entityType="song" slug={songSlug} />
      </main>
      <PublicFooter />
      </div>
    </div>
  );
}
