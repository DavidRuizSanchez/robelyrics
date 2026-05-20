import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { notFound } from "next/navigation";
import Breadcrumbs from "@/components/Breadcrumbs";
import MarkdownArticle from "@/components/MarkdownArticle";
import PersonAvatar from "@/components/PersonAvatar";
import MentionedInPosts from "@/components/MentionedInPosts";
import PublicFooter from "@/components/PublicFooter";
import PublicHeader from "@/components/PublicHeader";
import { apiFetch, ApiError } from "@/lib/api";
import { safeJsonLd } from "@/lib/safe-json-ld";

const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL || "https://entreinteriores.com";

export const revalidate = 3600;

type Membership = {
  artist_slug: string;
  artist_name: string;
  role: string;
  era: string | null;
  is_founder: boolean;
  is_current: boolean;
};

type WikidataRef = {
  name: string;
  wikidata_id: string;
  wikidata_url: string;
  wikipedia_url: string | null;
};

type ResolvedEntity = {
  type: string;
  name: string;
  canonical_id: string | null;
  url: string | null;
  same_as: string[];
  from_corpus: boolean;
};

type PersonDetail = {
  slug: string;
  full_name: string;
  stage_name: string | null;
  birth_date: string | null;
  death_date: string | null;
  birth_place: string | null;
  bio_short: string | null;
  wikipedia_url: string | null;
  wikidata_id: string | null;
  image_url: string | null;
  image_attribution: string | null;
  image_license: string | null;
  image_source_url: string | null;
  memberships: Membership[];
  other_bands: WikidataRef[];
  notable_works: WikidataRef[];
  occupations: WikidataRef[];
  entities: ResolvedEntity[];
  seo_body: string | null;
  seo_meta_title: string | null;
  seo_meta_description: string | null;
  schema_jsonld: Record<string, unknown> | null;
};

async function fetchPerson(slug: string): Promise<PersonDetail | null> {
  try {
    return await apiFetch<PersonDetail>(`/public/persons/${slug}`, {
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
  const detail = await fetchPerson(slug);
  if (!detail) return {};
  const title =
    detail.seo_meta_title ||
    `${detail.full_name} · Entre Interiores`;
  const description =
    detail.seo_meta_description ||
    detail.bio_short ||
    `Página sobre ${detail.full_name} en Entre Interiores.`;
  return {
    title,
    description,
    alternates: { canonical: `${SITE_URL}/personas/${slug}` },
    openGraph: {
      title,
      description,
      type: "profile",
      images: detail.image_url ? [{ url: detail.image_url }] : undefined,
    },
  };
}

function formatDateEs(iso: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso + "T00:00:00Z");
  return d.toLocaleDateString("es-ES", {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
}

function buildJsonLd(detail: PersonDetail): Record<string, unknown> {
  const sameAs: string[] = [];
  if (detail.wikipedia_url) sameAs.push(detail.wikipedia_url);
  if (detail.wikidata_id)
    sameAs.push(`https://www.wikidata.org/wiki/${detail.wikidata_id}`);

  const schema: Record<string, unknown> = {
    "@context": "https://schema.org",
    "@type": "Person",
    "@id": `${SITE_URL}/personas/${detail.slug}#person`,
    name: detail.full_name,
    url: `${SITE_URL}/personas/${detail.slug}`,
  };
  if (detail.stage_name && detail.stage_name !== detail.full_name) {
    schema.alternateName = detail.stage_name;
  }
  if (detail.birth_date) schema.birthDate = detail.birth_date;
  if (detail.death_date) schema.deathDate = detail.death_date;
  if (detail.birth_place) {
    schema.birthPlace = { "@type": "Place", name: detail.birth_place };
  }
  if (detail.image_url) schema.image = detail.image_url;
  if (sameAs.length > 0) schema.sameAs = sameAs;

  // memberOf combina: bandas del corpus (Extremoduro/Robe, con @id canónico
  // local) + bandas externas de Wikidata (con @id = Wikidata URL para que
  // Google sepa que son la misma entidad que la de su knowledge graph).
  const memberOf: Record<string, unknown>[] = [];
  for (const m of detail.memberships) {
    memberOf.push({
      "@type": "MusicGroup",
      "@id": `${SITE_URL}/${m.artist_slug}#musicgroup`,
      name: m.artist_name,
      url: `${SITE_URL}/${m.artist_slug}`,
    });
  }
  for (const b of detail.other_bands) {
    memberOf.push({
      "@type": "MusicGroup",
      "@id": b.wikidata_url,
      name: b.name,
      sameAs: [b.wikidata_url, ...(b.wikipedia_url ? [b.wikipedia_url] : [])],
    });
  }
  if (memberOf.length > 0) schema.memberOf = memberOf;

  if (detail.notable_works.length > 0) {
    schema.knowsAbout = detail.notable_works.map((w) => ({
      "@type": "CreativeWork",
      "@id": w.wikidata_url,
      name: w.name,
      sameAs: [w.wikidata_url, ...(w.wikipedia_url ? [w.wikipedia_url] : [])],
    }));
  }

  if (detail.occupations.length > 0) {
    schema.hasOccupation = detail.occupations.map((o) => ({
      "@type": "Occupation",
      name: o.name,
      sameAs: [o.wikidata_url],
    }));
  }

  // Entidades mentioned en el seo_content (lugares, otros músicos,
  // discos referidos en la biografía…). Person no soporta `mentions`
  // directamente en schema.org, así que las envolvemos como `knowsAbout`
  // (relacionado conceptualmente y aceptado por Google).
  if (detail.entities && detail.entities.length > 0) {
    const newMentions = detail.entities.map((e) => {
      const node: Record<string, unknown> = {
        "@type": e.type || "Thing",
        name: e.name,
      };
      if (e.canonical_id) node["@id"] = e.canonical_id;
      if (e.url) node.url = e.url;
      if (e.same_as && e.same_as.length > 0) node.sameAs = e.same_as;
      return node;
    });
    const prev = Array.isArray(schema.knowsAbout)
      ? (schema.knowsAbout as Record<string, unknown>[])
      : [];
    schema.knowsAbout = [...prev, ...newMentions];
  }

  return schema;
}

export default async function PersonPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const detail = await fetchPerson(slug);
  if (!detail) notFound();

  const birth = formatDateEs(detail.birth_date);
  const death = formatDateEs(detail.death_date);
  const yearBirth = detail.birth_date?.slice(0, 4);
  const yearDeath = detail.death_date?.slice(0, 4);
  const yearsLine = yearBirth
    ? `${yearBirth}${yearDeath ? `–${yearDeath}` : ""}`
    : null;

  const jsonLd = buildJsonLd(detail);

  return (
    <>
      <PublicHeader />
      <main className="px-5 md:px-14 py-10 md:py-14 max-w-[1100px] mx-auto">
        <Breadcrumbs
          className="mb-8"
          items={[
            { label: "Entre Interiores", href: "/" },
            { label: "Personas", href: "/personas" },
            {
              label: detail.stage_name || detail.full_name,
              href: `/personas/${detail.slug}`,
            },
          ]}
        />

        <article>
          <header className="grid grid-cols-1 md:grid-cols-[280px_1fr] gap-10 mb-12">
            {detail.image_url ? (
              <div>
                <div className="aspect-[3/4] overflow-hidden bg-divider/30 relative">
                  <Image
                    src={detail.image_url}
                    alt={`${detail.stage_name || detail.full_name}${detail.birth_place ? `, ${detail.birth_place}` : ""}${detail.birth_date ? ` · fotografía libre vía Wikimedia Commons` : ""}`}
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
                        // markdown links → html
                        .replace(
                          /\[([^\]]+)\]\(([^)]+)\)/g,
                          '<a href="$2" target="_blank" rel="noopener noreferrer" class="text-accent hover:underline">$1</a>',
                        )
                        // markdown italics → html
                        .replace(/\*([^*]+)\*/g, "<em>$1</em>"),
                    }}
                  />
                )}
              </div>
            ) : (
              <div className="aspect-[3/4] overflow-hidden relative">
                <PersonAvatar
                  name={detail.stage_name || detail.full_name}
                  slug={detail.slug}
                />
              </div>
            )}

            <div>
              {yearsLine && (
                <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-2">
                  {yearsLine}
                </p>
              )}
              <h1 className="font-serif text-5xl md:text-[64px] text-ink leading-[0.95] tracking-[-1.5px] m-0">
                {detail.stage_name || detail.full_name}
              </h1>
              {detail.stage_name && detail.stage_name !== detail.full_name && (
                <p className="font-serif italic text-ink-dim text-xl mt-3">
                  {detail.full_name}
                </p>
              )}
              {detail.bio_short && (
                <p className="font-serif text-ink-dim text-lg mt-6 leading-relaxed">
                  {detail.bio_short}
                </p>
              )}

              <dl className="mt-8 space-y-2 font-mono text-[11px] tracking-[1px] uppercase text-ink-faint">
                {birth && (
                  <div className="flex gap-4">
                    <dt className="w-32">nacimiento</dt>
                    <dd className="text-ink-dim normal-case tracking-normal font-serif">
                      {birth}
                      {detail.birth_place ? ` · ${detail.birth_place}` : ""}
                    </dd>
                  </div>
                )}
                {death && (
                  <div className="flex gap-4">
                    <dt className="w-32">fallecimiento</dt>
                    <dd className="text-ink-dim normal-case tracking-normal font-serif">
                      {death}
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

              {detail.memberships.length > 0 && (
                <div className="mt-8">
                  <p className="font-mono text-[10px] tracking-[3px] uppercase text-ink-faint mb-3">
                    pertenencias
                  </p>
                  <ul className="space-y-2">
                    {detail.memberships.map((m, i) => (
                      <li key={i} className="font-serif text-ink-dim">
                        <Link
                          href={`/${m.artist_slug}`}
                          data-cursor="hover"
                          className="text-accent hover:underline"
                        >
                          {m.artist_name}
                        </Link>{" "}
                        · {m.role}
                        {m.era && ` (${m.era})`}
                        {m.is_founder && (
                          <span className="font-mono text-[9px] tracking-[2px] uppercase text-ink-faint ml-2">
                            · fundador
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {detail.other_bands.length > 0 && (
                <div className="mt-8">
                  <p className="font-mono text-[10px] tracking-[3px] uppercase text-ink-faint mb-3">
                    otros proyectos
                  </p>
                  <ul className="space-y-2">
                    {detail.other_bands.map((b) => (
                      <li key={b.wikidata_id} className="font-serif text-ink-dim">
                        {b.wikipedia_url ? (
                          <a
                            href={b.wikipedia_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            data-cursor="hover"
                            className="text-accent hover:underline"
                          >
                            {b.name} ↗
                          </a>
                        ) : (
                          <span>{b.name}</span>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {detail.notable_works.length > 0 && (
                <div className="mt-8">
                  <p className="font-mono text-[10px] tracking-[3px] uppercase text-ink-faint mb-3">
                    obras destacadas
                  </p>
                  <ul className="space-y-2">
                    {detail.notable_works.map((w) => (
                      <li key={w.wikidata_id} className="font-serif text-ink-dim">
                        {w.wikipedia_url ? (
                          <a
                            href={w.wikipedia_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            data-cursor="hover"
                            className="text-accent hover:underline"
                          >
                            {w.name} ↗
                          </a>
                        ) : (
                          <span>{w.name}</span>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {detail.occupations.length > 0 && (
                <div className="mt-8">
                  <p className="font-mono text-[10px] tracking-[3px] uppercase text-ink-faint mb-3">
                    oficios
                  </p>
                  <p className="font-serif text-ink-dim leading-relaxed">
                    {detail.occupations.map((o) => o.name).join(" · ")}
                  </p>
                </div>
              )}
            </div>
          </header>

          {detail.seo_body && (
            <MarkdownArticle markdown={detail.seo_body} />
          )}
        </article>

        <MentionedInPosts
          slug={detail.slug}
          heading="Mencionado en el diario"
        />

        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: safeJsonLd(jsonLd) }}
        />
      </main>
      <PublicFooter />
    </>
  );
}
