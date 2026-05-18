import type { Metadata } from "next";
import Link from "next/link";
import Breadcrumbs from "@/components/Breadcrumbs";
import PublicFooter from "@/components/PublicFooter";
import PublicHeader from "@/components/PublicHeader";
import { apiFetch } from "@/lib/api";
import { safeJsonLd } from "@/lib/safe-json-ld";
import type { PublicSearchOut } from "@/lib/types";

const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL || "https://entreinteriores.com";

const KIND_LABEL: Record<string, string> = {
  artist: "Artista",
  album: "Disco",
  song: "Canción",
};

// La página `/buscar` sin query es un hub indexable (la SearchAction de
// WebSite apunta aquí). Las SERPs internas `/buscar?q=...` son `noindex`
// porque son thin content / duplicado de las páginas reales del catálogo.
// Google explícitamente desaconseja indexar este tipo de páginas.
export async function generateMetadata({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}): Promise<Metadata> {
  const { q } = await searchParams;
  const hasQuery = !!(q && q.trim());

  if (hasQuery) {
    return {
      title: `Buscar «${q}» · Entre Interiores`,
      description:
        "Resultados de búsqueda en el catálogo de Extremoduro y Robe.",
      robots: { index: false, follow: true },
      alternates: { canonical: `${SITE_URL}/buscar` },
    };
  }

  return {
    title: "Buscar canciones, discos y letras · Entre Interiores",
    description:
      "Buscador de canciones, discos y artistas de Extremoduro y Robe. Encuentra letras, contexto y análisis.",
    alternates: { canonical: `${SITE_URL}/buscar` },
  };
}

export default async function BuscarPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const { q } = await searchParams;
  const query = (q || "").trim();

  let data: PublicSearchOut | null = null;
  if (query.length >= 2) {
    try {
      data = await apiFetch<PublicSearchOut>(
        `/public/search?q=${encodeURIComponent(query)}`,
        { authenticated: false },
      );
    } catch {
      data = null;
    }
  }

  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "SearchResultsPage",
    url: query
      ? `${SITE_URL}/buscar?q=${encodeURIComponent(query)}`
      : `${SITE_URL}/buscar`,
    isPartOf: { "@type": "WebSite", url: SITE_URL, name: "Entre Interiores" },
  };

  return (
    <>
      <PublicHeader />
      <main className="px-5 md:px-14 py-10 md:py-14 max-w-[900px] mx-auto">
        <Breadcrumbs
          className="mb-8"
          items={[
            { label: "Entre Interiores", href: "/" },
            { label: "Buscar", href: "/buscar" },
          ]}
        />

        <header className="mb-10">
          <h1 className="font-serif text-4xl md:text-[56px] text-ink leading-[0.95] tracking-[-1.5px]">
            Buscar
          </h1>
          <p className="mt-4 font-serif text-lg text-ink-dim">
            Busca por título de canción, disco o artista en el catálogo de
            Extremoduro y Robe.
          </p>
        </header>

        <form
          action="/buscar"
          method="get"
          className="mb-12 flex flex-col sm:flex-row gap-3"
        >
          <input
            type="search"
            name="q"
            defaultValue={query}
            placeholder="ej. agila, mayéutica, prometeo…"
            aria-label="Buscar canciones, discos y artistas"
            className="flex-1 px-4 py-3 bg-paper border border-divider font-serif text-lg text-ink placeholder:text-ink-faint focus:outline-none focus:border-accent"
            minLength={2}
            required
          />
          <button
            type="submit"
            data-cursor="hover"
            className="px-6 py-3 bg-accent text-white font-mono text-[11px] tracking-[2.5px] uppercase hover:opacity-90"
          >
            Buscar
          </button>
        </form>

        {query && !data && (
          <p className="font-mono text-[11px] tracking-[2px] uppercase text-ink-faint">
            Error al consultar. Intenta de nuevo.
          </p>
        )}

        {data && (
          <section>
            <p className="font-mono text-[10px] tracking-[3px] uppercase text-ink-faint mb-6">
              {data.results.length} resultado{data.results.length === 1 ? "" : "s"} para «{query}»
            </p>

            {data.results.length === 0 ? (
              <p className="font-serif text-lg text-ink-dim">
                No hay coincidencias. Prueba con otra palabra o entra a la{" "}
                <Link
                  href="/discografia"
                  data-cursor="hover"
                  className="text-accent hover:underline"
                >
                  discografía completa
                </Link>
                .
              </p>
            ) : (
              <ul className="divide-y divide-divider">
                {data.results.map((hit) => (
                  <li key={`${hit.kind}-${hit.url_path}`}>
                    <Link
                      href={hit.url_path}
                      data-cursor="hover"
                      className="block py-4 group"
                    >
                      <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-1">
                        {KIND_LABEL[hit.kind] || hit.kind}
                      </p>
                      <p className="font-serif text-xl md:text-2xl text-ink leading-tight group-hover:text-accent transition-colors">
                        {hit.title}
                      </p>
                      {hit.subtitle && (
                        <p className="mt-1 font-mono text-[11px] tracking-[1px] text-ink-dim">
                          {hit.subtitle}
                        </p>
                      )}
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}

        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: safeJsonLd(jsonLd) }}
        />
      </main>
      <PublicFooter />
    </>
  );
}
