import Link from "next/link";
import { notFound } from "next/navigation";
import AlbumCover from "@/components/AlbumCover";
import Breadcrumbs from "@/components/Breadcrumbs";
import MarkdownArticle from "@/components/MarkdownArticle";
import PublicFooter from "@/components/PublicFooter";
import PublicHeader from "@/components/PublicHeader";
import { apiFetch, ApiError } from "@/lib/api";
import { safeJsonLd } from "@/lib/safe-json-ld";
import {
  buildGraph,
  musicAlbumNode,
  musicGroupNode,
  personNode,
} from "@/lib/schema-graph";
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
        <Breadcrumbs
          className="mb-8"
          items={[
            { label: "Entre Interiores", href: "/" },
            { label: detail.name, href: `/${artist}` },
          ]}
        />
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

        {detail.members && detail.members.length > 0 && (
          <section className="mt-20">
            <h2 className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-6">
              Quiénes — miembros del grupo
            </h2>
            <ul className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-6 md:gap-8">
              {detail.members.map((m) => (
                <li key={`${m.slug}-${m.era ?? ""}`}>
                  <Link
                    href={`/personas/${m.slug}`}
                    data-cursor="hover"
                    className="group block"
                  >
                    <div className="aspect-square bg-divider/30 overflow-hidden">
                      {m.image_url ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={m.image_url}
                          alt={m.full_name}
                          loading="lazy"
                          className="w-full h-full object-cover group-hover:scale-[1.02] transition-transform duration-500"
                        />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center font-mono text-[10px] uppercase tracking-[2px] text-ink-faint">
                          sin foto
                        </div>
                      )}
                    </div>
                    <p className="mt-3 font-serif text-[17px] md:text-lg text-ink leading-[1.25] transition-colors group-hover:text-accent">
                      {m.stage_name && m.stage_name !== m.full_name
                        ? m.stage_name
                        : m.full_name}
                    </p>
                    <p className="font-mono text-[10px] tracking-[2px] uppercase text-ink-faint mt-1">
                      {m.role}
                      {m.era && ` · ${m.era}`}
                      {m.is_founder && " · fundador"}
                    </p>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        )}

        {detail.seo_body && (
          <script
            type="application/ld+json"
            dangerouslySetInnerHTML={{
              __html: safeJsonLd(
                buildGraph([
                  musicGroupNode({
                    slug: artist,
                    name: detail.name,
                    activeYears: detail.active_years,
                    albums: detail.albums.map((a) => ({
                      slug: a.slug,
                      artistSlug: artist,
                      title: a.title,
                      year: a.year,
                      coverUrl: a.cover_url,
                    })),
                    members: detail.members.map((m) => ({
                      slug: m.slug,
                      fullName: m.full_name,
                      stageName: m.stage_name,
                    })),
                  }),
                  ...detail.albums.map((a) =>
                    musicAlbumNode({
                      slug: a.slug,
                      artistSlug: artist,
                      title: a.title,
                      year: a.year,
                      coverUrl: a.cover_url,
                    }),
                  ),
                  ...detail.members.map((m) =>
                    personNode({
                      slug: m.slug,
                      fullName: m.full_name,
                      stageName: m.stage_name,
                      imageUrl: m.image_url,
                      memberOf: [
                        { artistSlug: artist, artistName: detail.name },
                      ],
                    }),
                  ),
                ]),
              ),
            }}
          />
        )}
      </main>
      <PublicFooter />
    </>
  );
}
