import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import Breadcrumbs from "@/components/Breadcrumbs";
import PersonAvatar from "@/components/PersonAvatar";
import PublicFooter from "@/components/PublicFooter";
import PublicHeader from "@/components/PublicHeader";
import MarkdownArticle from "@/components/MarkdownArticle";
import { apiFetch, ApiError } from "@/lib/api";
import { safeJsonLd } from "@/lib/safe-json-ld";
import {
  bodyVideoNodes,
  breadcrumbListNode,
  buildGraph,
  canonical,
  itemListNode,
  webPageNode,
} from "@/lib/schema-graph";

const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL || "https://entreinteriores.com";

export const revalidate = 3600;

// Desde el 19-10-2026 el texto, el title y la description viven en la BD
// (`seo_content`, entity_type='page') para que una propuesta del blog pueda
// AMPLIAR esta página en vez de canibalizarla: es la que posiciona «integrantes
// de extremoduro». Estos son los valores de antes, que la migración sembró tal
// cual, y quedan de respaldo.
const FALLBACK = {
  title: "Integrantes de Extremoduro y los colegas de Robe · Entre Interiores",
  description:
    "Los integrantes de Extremoduro a lo largo de su historia, la banda solista de Robe y las voces amigas del universo: quién es quién y qué tocó cada uno.",
  h1: "Los colegas de Robe",
  intro:
    "Los miembros que pasaron por Extremoduro y la banda solista, las voces amigas que el escenario y los discos cruzaron con la suya.",
};

type IndexPage = {
  slug: string;
  h1: string | null;
  seo_body: string | null;
  seo_meta_title: string | null;
  seo_meta_description: string | null;
  seo_body_videos?: {
    youtube_id: string;
    title: string;
    kind: string;
    upload_date: string | null;
  }[];
};

// Solo un 404 cae al respaldo (instalación sin migrar). Cualquier otro fallo se
// propaga para que el ISR conserve la versión anterior en vez de cachear la
// página sin sus secciones.
async function getPage(): Promise<IndexPage | null> {
  try {
    return await apiFetch<IndexPage>("/public/pages/personas", { authenticated: false });
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  }
}

/** Lo que va antes del primer H2 (la intro) y el resto (las secciones). */
function partir(body: string | null): { intro: string; secciones: string } {
  const texto = (body || "").trim();
  const m = texto.match(/^##(?!#)/m);
  if (!m || m.index === undefined) return { intro: texto, secciones: "" };
  return { intro: texto.slice(0, m.index).trim(), secciones: texto.slice(m.index).trim() };
}

export async function generateMetadata(): Promise<Metadata> {
  const page = await getPage();
  return {
    title: page?.seo_meta_title || FALLBACK.title,
    description: page?.seo_meta_description || FALLBACK.description,
    alternates: { canonical: `${SITE_URL}/personas` },
  };
}

type PersonListItem = {
  slug: string;
  full_name: string;
  stage_name: string | null;
  birth_date: string | null;
  death_date: string | null;
  image_url: string | null;
};

function formatYear(iso: string | null): string | null {
  if (!iso) return null;
  return iso.slice(0, 4);
}

export default async function PersonasPage() {
  // Sin try/catch a propósito: la página se sirve cacheada (ISR). Si el API
  // falla al regenerar, Next conserva la versión anterior; tragarse el error
  // guardaría la lista vacía durante una hora.
  let items: PersonListItem[] = [];
  items = await apiFetch<PersonListItem[]>("/public/persons", {
    authenticated: false,
  });
  const page = await getPage();
  const h1 = page?.h1 || FALLBACK.h1;
  const { intro, secciones } = partir(page ? page.seo_body : FALLBACK.intro);
  // La intro de siempre es texto plano y conserva su estilo; si una ampliación
  // le mete enlaces o varios párrafos, se pinta como markdown.
  const introPlana = !/[\[\]*_#>\n]/.test(intro);

  return (
    <>
      <PublicHeader />
      <main className="px-5 md:px-14 py-10 md:py-14 max-w-[1100px] mx-auto">
        <Breadcrumbs
          className="mb-8"
          items={[
            { label: "Entre Interiores", href: "/" },
            { label: "Personas", href: "/personas" },
          ]}
        />

        <header className="mb-14">
          <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-2">
            los colegas
          </p>
          <h1 className="font-serif text-5xl md:text-[80px] text-ink leading-[0.95] tracking-[-2px] m-0">
            {h1}
          </h1>
          {intro &&
            (introPlana ? (
              <p className="font-serif italic text-ink-dim text-lg mt-6 max-w-2xl leading-relaxed">
                {intro}
              </p>
            ) : (
              <div className="mt-6 max-w-2xl">
                <MarkdownArticle markdown={intro} />
              </div>
            ))}
        </header>

        {items.length === 0 ? (
          <p className="font-serif italic text-ink-dim">
            Sin personas registradas todavía.
          </p>
        ) : (
          <ul className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-8 gap-y-12">
            {items.map((p) => {
              const yearBirth = formatYear(p.birth_date);
              const yearDeath = formatYear(p.death_date);
              const years = yearBirth
                ? `${yearBirth}${yearDeath ? `–${yearDeath}` : "–"}`
                : "";
              return (
                <li key={p.slug}>
                  <Link
                    href={`/personas/${p.slug}`}
                    data-cursor="hover"
                    className="group block"
                  >
                    <div className="aspect-[3/4] bg-divider/30 mb-4 overflow-hidden relative">
                      {p.image_url ? (
                        <Image
                          src={p.image_url}
                          alt={`Retrato de ${p.stage_name || p.full_name}${p.stage_name && p.stage_name !== p.full_name ? ` (${p.full_name})` : ""}`}
                          fill
                          sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw"
                          className="object-cover group-hover:scale-[1.02] transition-transform duration-500"
                        />
                      ) : (
                        <PersonAvatar
                          name={
                            p.stage_name && p.stage_name !== p.full_name
                              ? p.stage_name
                              : p.full_name
                          }
                          slug={p.slug}
                        />
                      )}
                    </div>
                    <h2 className="font-serif text-2xl text-ink group-hover:text-accent transition-colors leading-tight">
                      {p.stage_name && p.stage_name !== p.full_name
                        ? p.stage_name
                        : p.full_name}
                    </h2>
                    {p.stage_name && p.stage_name !== p.full_name && (
                      <p className="font-serif italic text-ink-dim text-sm mt-1">
                        {p.full_name}
                      </p>
                    )}
                    {years && (
                      <p className="font-mono text-[10px] tracking-[2px] uppercase text-ink-faint mt-2">
                        {years}
                      </p>
                    )}
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
        {secciones && (
          <section className="mt-20">
            <MarkdownArticle markdown={secciones} />
          </section>
        )}
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: safeJsonLd(
              buildGraph([
                ...bodyVideoNodes(
                  page?.seo_body_videos,
                  canonical.itemList("/personas"),
                  h1,
                ),
                webPageNode({
                  path: "/personas",
                  name: h1,
                  type: "CollectionPage",
                  mainEntityId: canonical.itemList("/personas"),
                }),
                itemListNode(
                  "/personas",
                  items.map((p) => ({
                    name: p.stage_name || p.full_name,
                    url: `/personas/${p.slug}`,
                    id: canonical.person(p.slug),
                  })),
                ),
                breadcrumbListNode("/personas", [
                  { name: "Entre Interiores", item: "/" },
                  { name: "Personas", item: "/personas" },
                ]),
              ]),
            ),
          }}
        />
      </main>
      <PublicFooter />
    </>
  );
}
