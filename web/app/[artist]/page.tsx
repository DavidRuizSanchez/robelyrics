import Link from "next/link";
import { notFound } from "next/navigation";
import AlbumCover from "@/components/AlbumCover";
import MarkdownArticle from "@/components/MarkdownArticle";
import PublicFooter from "@/components/PublicFooter";
import PublicHeader from "@/components/PublicHeader";
import { apiFetch, ApiError } from "@/lib/api";
import type { PublicArtistDetail } from "@/lib/types";

const VALID_SLUGS = new Set(["extremoduro", "robe"]);

export async function generateMetadata({
  params,
}: {
  params: Promise<{ artist: string }>;
}) {
  const { artist } = await params;
  if (!VALID_SLUGS.has(artist)) return {};
  try {
    const detail = await apiFetch<PublicArtistDetail>(`/public/artists/${artist}`, {
      authenticated: false,
    });
    if (!detail.seo_body) return {};
    return {
      title: detail.seo_meta_title || `${detail.name} · Entre Interiores`,
      description:
        detail.seo_meta_description ||
        `Discografía completa, contexto y análisis fan de ${detail.name}.`,
      openGraph: {
        title: detail.seo_meta_title || detail.name,
        description: detail.seo_meta_description || "",
        type: "website",
      },
    };
  } catch {
    return {};
  }
}

export default async function ArtistPublicPage({
  params,
}: {
  params: Promise<{ artist: string }>;
}) {
  const { artist } = await params;
  if (!VALID_SLUGS.has(artist)) notFound();

  let detail: PublicArtistDetail;
  try {
    detail = await apiFetch<PublicArtistDetail>(`/public/artists/${artist}`, {
      authenticated: false,
    });
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  // Si no hay seo_content publicado, página = 404 para crawlers
  if (!detail.seo_body) notFound();

  return (
    <>
      <PublicHeader />
      <main className="px-5 md:px-14 py-10 md:py-14 max-w-[1100px] mx-auto">
        <article>
          <header className="mb-12">
            <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-2">
              {detail.active_years || "—"}
            </p>
            <h1 className="font-serif text-5xl md:text-[80px] text-ink leading-[0.95] tracking-[-2px] m-0">
              {detail.seo_h1 || detail.name}
            </h1>
          </header>

          <MarkdownArticle markdown={detail.seo_body} />
        </article>

        <section className="mt-20">
          <h2 className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-6">
            Discografía
          </h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-6 md:gap-8">
            {detail.albums.map((alb) => (
              <Link
                key={alb.slug}
                href={`/${artist}/${alb.slug}`}
                data-cursor="hover"
                className="group block"
              >
                <AlbumCover
                  coverUrl={alb.cover_url}
                  slug={alb.slug}
                  title={alb.title}
                  variant="md"
                  className="!w-full !h-auto aspect-square"
                />
                <p className="mt-3 font-serif text-[17px] md:text-lg text-ink leading-[1.25] transition-colors group-hover:text-accent">
                  {alb.title}
                </p>
                <p className="font-mono text-[10px] tracking-[2px] uppercase text-ink-faint mt-1">
                  {alb.year} · {alb.kind}
                </p>
              </Link>
            ))}
          </div>
        </section>

        {detail.seo_body && (
          <script
            type="application/ld+json"
            dangerouslySetInnerHTML={{
              __html: JSON.stringify({
                "@context": "https://schema.org",
                "@type": "MusicGroup",
                name: detail.name,
                url: `/${artist}`,
                album: detail.albums.map((a) => ({
                  "@type": "MusicAlbum",
                  name: a.title,
                  datePublished: String(a.year),
                  url: `/${artist}/${a.slug}`,
                })),
              }),
            }}
          />
        )}
      </main>
      <PublicFooter />
    </>
  );
}
