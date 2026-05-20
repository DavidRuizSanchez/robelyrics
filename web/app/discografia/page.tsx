import type { Metadata } from "next";
import Link from "next/link";
import AlbumCover from "@/components/AlbumCover";
import Breadcrumbs from "@/components/Breadcrumbs";
import PublicFooter from "@/components/PublicFooter";
import PublicHeader from "@/components/PublicHeader";
import { apiFetch } from "@/lib/api";
import { safeJsonLd } from "@/lib/safe-json-ld";
import type { PublicArtistDetail } from "@/lib/types";

const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL || "https://entreinteriores.com";
const ARTIST_SLUGS = ["extremoduro", "robe"] as const;

export const revalidate = 3600;

export const metadata: Metadata = {
  title: "Discografía completa · Extremoduro y Robe · Entre Interiores",
  description:
    "Toda la discografía de Extremoduro y Robe en orden cronológico: cada disco enlaza a su análisis, contexto y letras comentadas.",
  alternates: { canonical: `${SITE_URL}/discografia` },
};

export default async function DiscografiaPage() {
  const artists = await Promise.all(
    ARTIST_SLUGS.map((slug) =>
      apiFetch<PublicArtistDetail>(`/public/artists/${slug}`, {
        authenticated: false,
      }),
    ),
  );

  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "CollectionPage",
    name: "Discografía completa · Extremoduro y Robe",
    url: `${SITE_URL}/discografia`,
    isPartOf: { "@type": "WebSite", url: SITE_URL, name: "Entre Interiores" },
    mainEntity: {
      "@type": "ItemList",
      itemListElement: artists.flatMap((a, ai) =>
        a.albums.map((alb, idx) => ({
          "@type": "ListItem",
          position: ai * 100 + idx + 1,
          url: `${SITE_URL}/${a.slug}/${alb.slug}`,
          name: `${alb.title} (${alb.year})`,
        })),
      ),
    },
  };

  return (
    <>
      <PublicHeader />
      <main className="px-5 md:px-14 py-10 md:py-14 max-w-[1100px] mx-auto">
        <Breadcrumbs
          className="mb-8"
          items={[
            { label: "Entre Interiores", href: "/" },
            { label: "Discografía", href: "/discografia" },
          ]}
        />

        <header className="mb-14">
          <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-3">
            catálogo completo
          </p>
          <h1 className="font-serif text-5xl md:text-[72px] text-ink leading-[0.95] tracking-[-2px] m-0">
            Discografía
          </h1>
          <p className="mt-6 max-w-[640px] font-serif text-lg md:text-xl text-ink-dim leading-relaxed">
            Toda la obra de Extremoduro y Robe, en orden cronológico.
            Cada disco abre a su contexto editorial, fragmentos citados de
            letras y enlaces a las canciones.
          </p>
        </header>

        {artists.map((a) => (
          <section key={a.slug} className="mb-20">
            <div className="flex items-baseline justify-between mb-8 border-b border-divider pb-4">
              <h2 className="font-serif text-3xl md:text-[40px] text-ink leading-tight m-0">
                <Link
                  href={`/${a.slug}`}
                  data-cursor="hover"
                  className="hover:text-accent"
                >
                  {a.name}
                </Link>
              </h2>
              <p className="font-mono text-[11px] tracking-[2px] uppercase text-ink-faint">
                {a.active_years} · {a.albums.length} discos
              </p>
            </div>

            <ol className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-6 md:gap-8">
              {a.albums.map((alb) => (
                <li key={alb.slug}>
                  <Link
                    href={`/${a.slug}/${alb.slug}`}
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
                </li>
              ))}
            </ol>
          </section>
        ))}

        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: safeJsonLd(jsonLd) }}
        />
      </main>
      <PublicFooter />
    </>
  );
}
