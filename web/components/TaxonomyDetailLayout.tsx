import Link from "next/link";
import Breadcrumbs from "@/components/Breadcrumbs";
import MarkdownArticle from "@/components/MarkdownArticle";
import PublicFooter from "@/components/PublicFooter";
import PublicHeader from "@/components/PublicHeader";
import { safeJsonLd } from "@/lib/safe-json-ld";
import type { PublicTaxonomyDetail } from "@/lib/types";

const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL || "https://entreinteriores.com";

type Props = {
  hubSlug: "temas" | "lugares" | "conceptos";
  hubLabel: string;
  detail: PublicTaxonomyDetail;
};

export default function TaxonomyDetailLayout({ hubSlug, hubLabel, detail }: Props) {
  const isPlace = detail.kind === "place" && detail.extra?.geo_lat && detail.extra?.geo_lng;

  const collection = {
    "@context": "https://schema.org",
    "@type": "CollectionPage",
    name: detail.name,
    description: detail.description ?? undefined,
    url: `${SITE_URL}/${hubSlug}/${detail.slug}`,
    isPartOf: { "@type": "WebSite", url: SITE_URL, name: "Entre Interiores" },
    mainEntity: {
      "@type": "ItemList",
      itemListElement: detail.songs.map((s, i) => ({
        "@type": "ListItem",
        position: i + 1,
        url: `${SITE_URL}${s.url_path}`,
        name: `${s.title} — ${s.artist_name} · ${s.album_title}`,
      })),
    },
  };

  const placeJsonLd = isPlace
    ? {
        "@context": "https://schema.org",
        "@type": "Place",
        name: detail.name,
        description: detail.description ?? undefined,
        geo: {
          "@type": "GeoCoordinates",
          latitude: detail.extra!.geo_lat,
          longitude: detail.extra!.geo_lng,
        },
      }
    : null;

  return (
    <>
      <PublicHeader />
      <main className="px-5 md:px-14 py-10 md:py-14 max-w-[1000px] mx-auto">
        <Breadcrumbs
          className="mb-8"
          items={[
            { label: "Entre Interiores", href: "/" },
            { label: hubLabel, href: `/${hubSlug}` },
            { label: detail.name, href: `/${hubSlug}/${detail.slug}` },
          ]}
        />

        <header className="mb-12">
          <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-3">
            {hubLabel} · {detail.songs.length} canción
            {detail.songs.length === 1 ? "" : "es"}
          </p>
          <h1 className="font-serif text-5xl md:text-[72px] text-ink leading-[0.95] tracking-[-2px] m-0">
            {detail.name}
          </h1>
        </header>

        {detail.description && (
          <section className="mb-12 max-w-[700px]">
            <MarkdownArticle markdown={detail.description} />
          </section>
        )}

        <section>
          <h2 className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-5">
            Canciones
          </h2>
          <ul className="divide-y divide-divider">
            {detail.songs.map((s) => (
              <li key={s.url_path}>
                <Link
                  href={s.url_path}
                  data-cursor="hover"
                  className="block py-4 group"
                >
                  <p className="font-serif text-xl md:text-2xl text-ink group-hover:text-accent transition-colors leading-tight">
                    {s.title}
                  </p>
                  <p className="mt-1 font-mono text-[11px] tracking-[1px] text-ink-dim">
                    {s.artist_name} · {s.album_title}
                    {s.year ? ` (${s.year})` : ""}
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        </section>

        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: safeJsonLd(collection) }}
        />
        {placeJsonLd && (
          <script
            type="application/ld+json"
            dangerouslySetInnerHTML={{ __html: safeJsonLd(placeJsonLd) }}
          />
        )}
      </main>
      <PublicFooter />
    </>
  );
}
