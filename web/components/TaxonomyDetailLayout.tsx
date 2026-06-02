import Image from "next/image";
import Link from "next/link";
import Breadcrumbs from "@/components/Breadcrumbs";
import MarkdownArticle from "@/components/MarkdownArticle";
import RelatedPosts from "@/components/RelatedPosts";
import PublicFooter from "@/components/PublicFooter";
import PublicHeader from "@/components/PublicHeader";
import { safeJsonLd } from "@/lib/safe-json-ld";
import {
  breadcrumbListNode,
  buildGraph,
  canonical,
  itemListNode,
  mentionsArray,
  webPageNode,
} from "@/lib/schema-graph";
import type { TaxonomyKind } from "@/lib/schema-graph";
import type { PublicTaxonomyDetail } from "@/lib/types";

const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL || "https://entreinteriores.com";

type Props = {
  hubSlug: "temas" | "lugares" | "conceptos";
  hubLabel: string;
  detail: PublicTaxonomyDetail;
};

export default function TaxonomyDetailLayout({ hubSlug, hubLabel, detail }: Props) {
  const kind = detail.kind as TaxonomyKind;
  const isPlace = kind === "place" && detail.extra?.geo_lat && detail.extra?.geo_lng;
  const path = `/${hubSlug}/${detail.slug}`;
  const mentions = mentionsArray(detail.entities);

  // Nodo de la taxonomía: Place (con geo) para lugares; DefinedTerm para temas
  // y conceptos. El JSON-LD usa solo el meta description SEO (texto plano).
  const taxNode: Record<string, unknown> = {
    "@type": isPlace ? "Place" : "DefinedTerm",
    "@id": canonical.taxonomy(kind, detail.slug),
    name: detail.name,
    url: `${SITE_URL}${path}`,
  };
  if (detail.seo_meta_description) taxNode.description = detail.seo_meta_description;
  if (detail.image_url) taxNode.image = detail.image_url;
  if (isPlace) {
    taxNode.geo = {
      "@type": "GeoCoordinates",
      latitude: detail.extra!.geo_lat,
      longitude: detail.extra!.geo_lng,
    };
  }

  const collectionPage = webPageNode({
    path,
    name: detail.name,
    type: "CollectionPage",
    description: detail.seo_meta_description,
    mainEntityId: canonical.itemList(path),
  });
  if (mentions.length > 0) collectionPage.mentions = mentions;

  const graph = buildGraph([
    taxNode,
    itemListNode(
      path,
      detail.songs.map((s) => ({
        name: `${s.title}, ${s.artist_name}, ${s.album_title}`,
        url: s.url_path,
        id: `${SITE_URL}${s.url_path}#musiccomposition`,
      })),
    ),
    collectionPage,
    breadcrumbListNode(path, [
      { name: "Entre Interiores", item: "/" },
      { name: hubLabel, item: `/${hubSlug}` },
      { name: detail.name, item: path },
    ]),
  ]);

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

        {detail.image_url && (
          <figure className="mb-12">
            <div className="relative w-full aspect-[16/9] overflow-hidden rounded-sm border border-divider">
              <Image
                src={detail.image_url}
                alt={
                  detail.kind === "place"
                    ? `Fotografía de ${detail.name}`
                    : `Ilustración del ${detail.kind === "theme" ? "tema" : "símbolo"} «${detail.name}» en el universo de Robe y Extremoduro`
                }
                fill
                sizes="(max-width: 1100px) 100vw, 1100px"
                className="object-cover"
                priority
              />
            </div>
            {detail.image_attribution && (
              <figcaption className="mt-2 font-mono text-[10px] tracking-[1px] text-ink-faint">
                {detail.image_attribution}
              </figcaption>
            )}
          </figure>
        )}

        {detail.seo_body ? (
          <section className="mb-12">
            <MarkdownArticle markdown={detail.seo_body} />
          </section>
        ) : (
          detail.description && (
            <section className="mb-12 max-w-[700px]">
              <MarkdownArticle markdown={detail.description} />
            </section>
          )
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

        <RelatedPosts entityType={detail.kind} slug={detail.slug} />

        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: safeJsonLd(graph) }}
        />
      </main>
      <PublicFooter />
    </>
  );
}
