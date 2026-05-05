import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import AlbumCover from "@/components/AlbumCover";
import MarkdownArticle from "@/components/MarkdownArticle";
import PublicFooter from "@/components/PublicFooter";
import PublicHeader from "@/components/PublicHeader";
import { apiFetch, ApiError } from "@/lib/api";
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
    if (!detail.seo_body) return { robots: { index: false, follow: false } };
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
      if (matched) redirect(`/${artist}/${album}/${matched}`);
      notFound();
    }
    throw e;
  }
  if (!detail.seo_body) notFound();

  return (
    <>
      <PublicHeader />
      <main className="px-5 md:px-14 py-10 md:py-14 max-w-[1100px] mx-auto">
        <nav className="flex items-center gap-2 font-mono text-[11px] tracking-[2px] uppercase text-ink-dim mb-6">
          <Link href={`/${artist}`} data-cursor="hover" className="hover:text-ink">
            {detail.artist.name}
          </Link>
          <span className="opacity-50">·</span>
          <Link href={`/${artist}/${album}`} data-cursor="hover" className="hover:text-ink">
            {detail.album.title}
          </Link>
          <span className="text-ink-faint">({detail.album.year})</span>
        </nav>

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

        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: JSON.stringify({
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
    </>
  );
}
