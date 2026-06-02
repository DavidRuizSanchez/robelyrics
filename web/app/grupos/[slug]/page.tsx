import type { Metadata } from "next";
import Image from "next/image";
import { notFound } from "next/navigation";
import Breadcrumbs from "@/components/Breadcrumbs";
import MarkdownArticle from "@/components/MarkdownArticle";
import RelatedPosts from "@/components/RelatedPosts";
import PublicFooter from "@/components/PublicFooter";
import PublicHeader from "@/components/PublicHeader";
import { apiFetch, ApiError } from "@/lib/api";
import { safeJsonLd } from "@/lib/safe-json-ld";
import {
  asNode,
  breadcrumbListNode,
  buildGraph,
  canonical,
  webPageNode,
} from "@/lib/schema-graph";

const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL || "https://entreinteriores.com";

export const revalidate = 3600;

type ResolvedEntity = {
  type: string;
  name: string;
  canonical_id: string | null;
  url: string | null;
  same_as: string[];
  from_corpus: boolean;
};

type BandDetail = {
  slug: string;
  name: string;
  kind: string;
  founded_year: number | null;
  dissolved_year: number | null;
  bio_short: string | null;
  related_note: string | null;
  wikipedia_url: string | null;
  wikidata_id: string | null;
  image_url: string | null;
  image_attribution: string | null;
  image_license: string | null;
  image_source_url: string | null;
  members: string[];
  entities: ResolvedEntity[];
  seo_body: string | null;
  seo_meta_title: string | null;
  seo_meta_description: string | null;
  schema_jsonld: Record<string, unknown> | null;
};

async function fetchBand(slug: string): Promise<BandDetail | null> {
  try {
    return await apiFetch<BandDetail>(`/public/bands/${slug}`, {
      authenticated: false,
    });
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  }
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const detail = await fetchBand(slug);
  if (!detail) return {};
  const title = detail.seo_meta_title || `${detail.name} · Entre Interiores`;
  const description =
    detail.seo_meta_description ||
    detail.bio_short ||
    `${detail.name}, grupo afín al universo de Extremoduro y Robe.`;
  return {
    title,
    description,
    alternates: { canonical: `${SITE_URL}/grupos/${slug}` },
    openGraph: {
      title,
      description,
      type: "profile",
      images: detail.image_url ? [{ url: detail.image_url }] : undefined,
    },
  };
}

function buildJsonLd(detail: BandDetail): Record<string, unknown> {
  const sameAs: string[] = [];
  if (detail.wikipedia_url) sameAs.push(detail.wikipedia_url);
  if (detail.wikidata_id)
    sameAs.push(`https://www.wikidata.org/wiki/${detail.wikidata_id}`);

  const isLabel = detail.kind === "label";
  const schema: Record<string, unknown> = {
    "@context": "https://schema.org",
    "@type": isLabel ? "Organization" : "MusicGroup",
    "@id": `${SITE_URL}/grupos/${detail.slug}#${isLabel ? "organization" : "musicgroup"}`,
    name: detail.name,
    url: `${SITE_URL}/grupos/${detail.slug}`,
  };
  if (detail.founded_year) schema.foundingDate = String(detail.founded_year);
  if (detail.dissolved_year)
    schema.dissolutionDate = String(detail.dissolved_year);
  if (detail.image_url) schema.image = detail.image_url;
  if (sameAs.length > 0) schema.sameAs = sameAs;
  if (detail.members.length > 0) {
    schema.member = detail.members.map((m) => ({
      "@type": "Person",
      name: m.split(" · ")[0],
    }));
  }

  // Entidades mencionadas en el artículo (Extremoduro, Robe, discos…) como
  // knowsAbout para tejer el knowledge graph.
  if (detail.entities && detail.entities.length > 0) {
    schema.knowsAbout = detail.entities.map((e) => {
      const node: Record<string, unknown> = {
        "@type": e.type || "Thing",
        name: e.name,
      };
      if (e.canonical_id) node["@id"] = e.canonical_id;
      if (e.url) node.url = e.url;
      if (e.same_as && e.same_as.length > 0) node.sameAs = e.same_as;
      return node;
    });
  }

  return schema;
}

export default async function GrupoPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const detail = await fetchBand(slug);
  if (!detail) notFound();

  const years = detail.founded_year
    ? `${detail.founded_year}${detail.dissolved_year ? `–${detail.dissolved_year}` : ""}`
    : null;
  const kindLabel = detail.kind === "label" ? "sello discográfico" : "grupo";
  const path = `/grupos/${detail.slug}`;
  const jsonLd = buildGraph([
    asNode(buildJsonLd(detail)),
    webPageNode({
      path,
      name: detail.name,
      type: "ProfilePage",
      description: detail.seo_meta_description,
      mainEntityId: canonical.band(detail.slug, detail.kind === "label"),
    }),
    breadcrumbListNode(path, [
      { name: "Entre Interiores", item: "/" },
      { name: "Grupos", item: "/grupos" },
      { name: detail.name, item: path },
    ]),
  ]);

  return (
    <>
      <PublicHeader />
      <main className="px-5 md:px-14 py-10 md:py-14 max-w-[1100px] mx-auto">
        <Breadcrumbs
          className="mb-8"
          items={[
            { label: "Entre Interiores", href: "/" },
            { label: "Grupos", href: "/grupos" },
            { label: detail.name, href: `/grupos/${detail.slug}` },
          ]}
        />

        <article>
          <header className="grid grid-cols-1 md:grid-cols-[280px_1fr] gap-10 mb-12">
            {detail.image_url ? (
              <div>
                <div className="aspect-[3/4] overflow-hidden bg-divider/30 relative">
                  <Image
                    src={detail.image_url}
                    alt={`${detail.name}, ${kindLabel} afín a Extremoduro y Robe`}
                    fill
                    sizes="(max-width: 768px) 100vw, 280px"
                    priority
                    className="object-cover"
                  />
                </div>
                {detail.image_attribution && (
                  <p
                    className="font-mono text-[10px] tracking-[1px] text-ink-faint mt-2 leading-relaxed"
                    dangerouslySetInnerHTML={{
                      __html: detail.image_attribution
                        .replace(
                          /\[([^\]]+)\]\(([^)]+)\)/g,
                          '<a href="$2" target="_blank" rel="noopener noreferrer" class="text-accent hover:underline">$1</a>',
                        )
                        .replace(/\*([^*]+)\*/g, "<em>$1</em>"),
                    }}
                  />
                )}
              </div>
            ) : (
              <div className="aspect-[3/4] overflow-hidden relative bg-divider/30 flex items-center justify-center">
                <span className="font-serif text-ink-faint text-7xl select-none">
                  {detail.name.charAt(0)}
                </span>
              </div>
            )}

            <div>
              <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-2">
                {kindLabel}
                {years ? ` · ${years}` : ""}
              </p>
              <h1 className="font-serif text-5xl md:text-[64px] text-ink leading-[0.95] tracking-[-1.5px] m-0">
                {detail.name}
              </h1>
              {detail.bio_short && (
                <p className="font-serif text-ink-dim text-lg mt-6 leading-relaxed">
                  {detail.bio_short}
                </p>
              )}
              {detail.related_note && (
                <p className="font-serif italic text-ink-dim text-base mt-4 leading-relaxed border-l-2 border-accent/40 pl-4">
                  {detail.related_note}
                </p>
              )}

              <dl className="mt-8 space-y-2 font-mono text-[11px] tracking-[1px] uppercase text-ink-faint">
                {detail.members.length > 0 && (
                  <div className="flex gap-4">
                    <dt className="w-32">formación</dt>
                    <dd className="text-ink-dim normal-case tracking-normal font-serif">
                      {detail.members.join(" · ")}
                    </dd>
                  </div>
                )}
                {detail.wikipedia_url && (
                  <div className="flex gap-4">
                    <dt className="w-32">wikipedia</dt>
                    <dd>
                      <a
                        href={detail.wikipedia_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-accent hover:underline normal-case tracking-normal font-serif"
                      >
                        ficha completa ↗
                      </a>
                    </dd>
                  </div>
                )}
              </dl>
            </div>
          </header>

          {detail.seo_body && <MarkdownArticle markdown={detail.seo_body} />}
        </article>

        <RelatedPosts entityType="band" slug={detail.slug} />

        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: safeJsonLd(jsonLd) }}
        />
      </main>
      <PublicFooter />
    </>
  );
}
