import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import AlbumCover from "@/components/AlbumCover";
import Breadcrumbs from "@/components/Breadcrumbs";
import PublicFooter from "@/components/PublicFooter";
import PublicHeader from "@/components/PublicHeader";
import { apiFetch } from "@/lib/api";
import { safeJsonLd } from "@/lib/safe-json-ld";
import { asNode, breadcrumbListNode, buildGraph } from "@/lib/schema-graph";
import type { PublicAlbumOut, PublicArtistDetail } from "@/lib/types";

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || "https://entreinteriores.com";

export const revalidate = 3600;
// Solo los dos artistas del corpus: cualquier otro slug es 404, no una página vacía.
export const dynamicParams = false;

// Cada discografía tiene URL, contenido y metadata PROPIOS. Antes vivían como
// `/discografia?artist=X`: mismo H1, mismo cuerpo y canónica al hub, así que
// Google nunca las trataba como páginas. La demanda existe y está medida
// (DataForSEO ES, jul-2026): «discografia extremoduro» 4.400/mes,
// «albumes de extremoduro» 1.900, «discos de extremoduro» 1.300;
// «robe discografia» 390, «discografia robe» 320, «discos de robe» 320.
// OJO: «discografia los robe» tiene 0 búsquedas — el nombre del proyecto no es
// como lo busca la gente, así que el foco es «discografía de Robe».
const ARTISTS = {
  extremoduro: {
    display: "Extremoduro",
    // La regla del proyecto prohíbe «Robe Iniesta» en el contenido; aquí no aplica.
    intro: "el grupo de Robe",
    kicker: "la obra completa",
    alias: null,
    aliasNota: null,
  },
  robe: {
    display: "Robe",
    intro: "el proyecto en solitario de Roberto Iniesta tras Extremoduro",
    kicker: "en solitario",
    // El proyecto se llama «Los Robe» (así figura en su tienda oficial), aunque
    // la gente lo busca como «Robe» a secas: el nombre propio va en el cuerpo y
    // en el schema, no en el H1.
    alias: "Los Robe",
    // Solo lo comprobado: la tienda oficial (tienda.robe.es) usa «los Robe» para
    // el proyecto. Que aparezca así acreditado en los discos no lo he verificado,
    // y en una web pública no se afirma lo que no se ha mirado.
    aliasNota:
      "El proyecto se llama Los Robe, que es como figura en su tienda oficial, aunque casi todo el mundo lo busca como Robe a secas.",
  },
} as const;

type ArtistSlug = keyof typeof ARTISTS;

export function generateStaticParams() {
  return Object.keys(ARTISTS).map((artist) => ({ artist }));
}

function isArtist(slug: string): slug is ArtistSlug {
  return slug in ARTISTS;
}

async function getArtist(slug: ArtistSlug) {
  return apiFetch<PublicArtistDetail>(`/public/artists/${slug}`, { authenticated: false });
}

/** Cuentas reales del catálogo. Ni un número aquí sale de otro sitio. */
function stats(albums: PublicAlbumOut[]) {
  const years = albums.map((a) => a.year).filter(Boolean).sort((a, b) => a - b);
  const porTipo = albums.reduce<Record<string, number>>((acc, a) => {
    acc[a.kind] = (acc[a.kind] || 0) + 1;
    return acc;
  }, {});
  return {
    total: albums.length,
    primero: albums.find((a) => a.year === years[0]),
    ultimo: [...albums].reverse().find((a) => a.year === years[years.length - 1]),
    desde: years[0],
    hasta: years[years.length - 1],
    estudio: porTipo.studio || 0,
    directo: porTipo.live || 0,
    ep: porTipo.ep || 0,
  };
}

const KIND_LABEL: Record<string, string> = {
  studio: "estudio",
  live: "directo",
  ep: "EP",
  compilation: "recopilatorio",
};

/** Frase de inventario, construida solo con lo que dice el catálogo. */
function resumen(s: ReturnType<typeof stats>, display: string) {
  const partes = [
    s.estudio ? `${s.estudio} de estudio` : null,
    s.directo ? `${s.directo} en directo` : null,
    s.ep ? `${s.ep} EP` : null,
  ].filter(Boolean);
  const cuantos = `${s.total} ${s.total === 1 ? "disco" : "discos"}`;
  const periodo = `entre ${s.desde} y ${s.hasta}`;
  // Si son todos del mismo tipo, el desglose sobra («4 discos: 4 de estudio»).
  if (s.estudio === s.total) {
    return `${display} tiene ${cuantos} de estudio publicados ${periodo}.`;
  }
  return `${display} tiene ${cuantos} publicados ${periodo}${partes.length ? `: ${partes.join(", ")}` : ""}.`;
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ artist: string }>;
}): Promise<Metadata> {
  const { artist } = await params;
  if (!isArtist(artist)) return {};
  const { display } = ARTISTS[artist];
  const data = await getArtist(artist);
  const s = stats(data.albums);
  return {
    title: `Discografía de ${display} · todos los discos en orden · Entre Interiores`,
    description:
      `Los ${s.total} discos de ${display} en orden cronológico, de ${s.desde} a ${s.hasta}. ` +
      `Año, formato y canciones de cada álbum, con sus letras comentadas disco a disco.`,
    alternates: { canonical: `${SITE_URL}/discografia/${artist}` },
    openGraph: {
      title: `Discografía de ${display}`,
      description: resumen(s, display),
      url: `${SITE_URL}/discografia/${artist}`,
      type: "website",
    },
  };
}

export default async function DiscografiaArtistaPage({
  params,
}: {
  params: Promise<{ artist: string }>;
}) {
  const { artist } = await params;
  if (!isArtist(artist)) notFound();

  const { display, intro, kicker, alias, aliasNota } = ARTISTS[artist];
  const data = await getArtist(artist);
  const albums = [...data.albums].sort((a, b) => a.year - b.year);
  const s = stats(albums);
  const otro = artist === "extremoduro" ? "robe" : "extremoduro";
  const otroNombre = ARTISTS[otro].display;

  // Agrupación por década: da estructura de lectura sin inventarse etapas.
  // En castellano las del siglo XX se nombran con dos cifras («los 90»), las de
  // este con las cuatro («los 2000»); «los 1990» no lo dice nadie.
  const decadas = albums.reduce<Record<string, PublicAlbumOut[]>>((acc, a) => {
    const inicio = Math.floor(a.year / 10) * 10;
    const d = inicio < 2000 ? `${inicio - 1900}` : `${inicio}`;
    (acc[d] ||= []).push(a);
    return acc;
  }, {});

  const estudio = albums.filter((a) => a.kind === "studio");
  const otrosFormatos = albums.filter((a) => a.kind !== "studio");

  const faqs = [
    {
      q: `¿Cuántos discos tiene ${display}?`,
      a: resumen(s, display),
    },
    s.estudio !== s.total && {
      q: `¿Cuántos álbumes de estudio tiene ${display}?`,
      a:
        `${s.estudio}, desde «${estudio[0]?.title}» (${estudio[0]?.year}) hasta ` +
        `«${estudio[estudio.length - 1]?.title}» (${estudio[estudio.length - 1]?.year}). ` +
        `El resto son ${otrosFormatos.map((a) => `«${a.title}»`).join(", ")}.`,
    },
    s.primero && {
      q: `¿Cuál fue el primer disco de ${display}?`,
      a: `«${s.primero.title}», de ${s.primero.year}.`,
    },
    s.ultimo && {
      q: `¿Cuál es el último disco de ${display}?`,
      a: `«${s.ultimo.title}», de ${s.ultimo.year}.`,
    },
    alias && {
      q: `¿Cómo se llama la banda de ${display}?`,
      a: `${aliasNota} Por eso su discografía en solitario aparece a veces como discografía de ${alias}.`,
    },
  ].filter(Boolean) as { q: string; a: string }[];

  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "CollectionPage",
    name: `Discografía de ${display}`,
    url: `${SITE_URL}/discografia/${artist}`,
    description: resumen(s, display),
    about: {
      "@type": "MusicGroup",
      name: display,
      // El proyecto de Robe se llama «Los Robe»: va como nombre alternativo para
      // que los buscadores enlacen las dos formas sin canibalizar el H1.
      ...(alias ? { alternateName: [alias, data.name].filter((n) => n !== display) } : {}),
      url: `${SITE_URL}/${artist}`,
      album: albums.map((alb) => ({
        "@type": "MusicAlbum",
        name: alb.title,
        datePublished: String(alb.year),
        url: `${SITE_URL}/${artist}/${alb.slug}`,
      })),
    },
    mainEntity: {
      "@type": "ItemList",
      numberOfItems: albums.length,
      itemListElement: albums.map((alb, i) => ({
        "@type": "ListItem",
        position: i + 1,
        url: `${SITE_URL}/${artist}/${alb.slug}`,
        name: `${alb.title} (${alb.year})`,
      })),
    },
  };

  const faqLd = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: faqs.map((f) => ({
      "@type": "Question",
      name: f.q,
      acceptedAnswer: { "@type": "Answer", text: f.a },
    })),
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
            { label: display, href: `/discografia/${artist}` },
          ]}
        />

        <header className="mb-12">
          <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-3">
            {kicker}
          </p>
          <h1 className="font-serif text-5xl md:text-[68px] text-ink leading-[0.95] tracking-[-2px] m-0">
            Discografía de {display}
          </h1>
          <p className="mt-6 max-w-[680px] font-serif text-lg md:text-xl text-ink-dim leading-relaxed">
            Todos los discos de {display}, {intro}, en orden de publicación. {resumen(s, display)}{" "}
            Cada uno abre a su historia, su tracklist y sus letras comentadas.
          </p>
          {aliasNota && (
            <p className="mt-4 max-w-[680px] font-serif text-lg text-ink-dim leading-relaxed">
              {aliasNota}
            </p>
          )}
        </header>

        <dl className="grid grid-cols-2 md:grid-cols-4 gap-px bg-divider/60 border border-divider mb-16">
          {[
            { k: "discos", v: String(s.total) },
            { k: "de estudio", v: String(s.estudio) },
            { k: "primero", v: String(s.desde) },
            { k: "último", v: String(s.hasta) },
          ].map((item) => (
            <div key={item.k} className="bg-bg px-5 py-4">
              <dt className="font-mono text-[10px] tracking-[2px] uppercase text-ink-faint">
                {item.k}
              </dt>
              <dd className="font-serif text-3xl text-ink mt-1 m-0">{item.v}</dd>
            </div>
          ))}
        </dl>

        {Object.entries(decadas).map(([decada, discos]) => (
          <section key={decada} className="mb-16">
            <h2 className="font-serif text-3xl md:text-[38px] text-ink leading-tight mb-6 border-b border-divider pb-3">
              {display} en los {decada}
            </h2>
            <ol className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-6 md:gap-8">
              {discos.map((alb) => (
                <li key={alb.slug}>
                  <Link href={`/${artist}/${alb.slug}`} data-cursor="hover" className="group block">
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
                      {alb.year} · {KIND_LABEL[alb.kind] || alb.kind}
                    </p>
                  </Link>
                </li>
              ))}
            </ol>
          </section>
        ))}

        <section className="mb-16">
          <h2 className="font-serif text-3xl md:text-[38px] text-ink leading-tight mb-8 border-b border-divider pb-3">
            Todos los discos de {display}, uno a uno
          </h2>
          {/* Partido por formato: «álbumes de Extremoduro» (1.900 búsquedas/mes) y
              «discos de Extremoduro» (1.300) son consultas distintas de la genérica,
              y así cada una tiene su encabezado sin repetir ni un disco. */}
          {[
            { key: "estudio", titulo: `Álbumes de estudio de ${display}`, lista: estudio },
            { key: "otros", titulo: `Directos, EP y recopilatorios de ${display}`, lista: otrosFormatos },
          ]
            .filter((bloque) => bloque.lista.length > 0)
            .map((bloque) => (
              <div key={bloque.key} className="mb-10 last:mb-0">
                <h3 className="font-serif text-2xl text-ink mb-4">{bloque.titulo}</h3>
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse">
                    <thead>
                      <tr className="font-mono text-[10px] tracking-[2px] uppercase text-ink-faint">
                        <th className="py-3 pr-4 font-normal border-b border-divider">Año</th>
                        <th className="py-3 pr-4 font-normal border-b border-divider">Disco</th>
                        <th className="py-3 font-normal border-b border-divider">Formato</th>
                      </tr>
                    </thead>
                    <tbody>
                      {bloque.lista.map((alb) => (
                        <tr key={alb.slug} className="border-b border-divider/40">
                          <td className="py-3 pr-4 font-mono text-[13px] text-ink-faint align-top">
                            {alb.year}
                          </td>
                          <td className="py-3 pr-4 font-serif text-[17px] text-ink align-top">
                            <Link
                              href={`/${artist}/${alb.slug}`}
                              data-cursor="hover"
                              className="hover:text-accent"
                            >
                              {alb.title}
                            </Link>
                          </td>
                          <td className="py-3 font-mono text-[11px] tracking-[1px] uppercase text-ink-faint align-top">
                            {KIND_LABEL[alb.kind] || alb.kind}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ))}
        </section>

        <section className="mb-16">
          <h2 className="font-serif text-3xl md:text-[38px] text-ink leading-tight mb-6 border-b border-divider pb-3">
            Preguntas frecuentes sobre la discografía de {display}
          </h2>
          <dl className="space-y-6 max-w-[720px]">
            {faqs.map((f) => (
              <div key={f.q}>
                <dt className="font-serif text-xl text-ink">{f.q}</dt>
                <dd className="mt-1 font-serif text-lg text-ink-dim leading-relaxed m-0">{f.a}</dd>
              </div>
            ))}
          </dl>
        </section>

        <nav className="border-t border-divider pt-8 flex flex-wrap gap-x-8 gap-y-3 font-mono text-[11px] tracking-[2px] uppercase">
          <Link href={`/discografia/${otro}`} data-cursor="hover" className="text-accent hover:text-ink">
            Discografía de {otroNombre}
          </Link>
          <Link href={`/${artist}`} data-cursor="hover" className="text-ink-dim hover:text-ink">
            Historia de {display}
          </Link>
          <Link href="/discografia" data-cursor="hover" className="text-ink-dim hover:text-ink">
            Toda la discografía
          </Link>
        </nav>

        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: safeJsonLd(
              buildGraph([
                asNode(jsonLd),
                asNode(faqLd),
                breadcrumbListNode(`/discografia/${artist}`, [
                  { name: "Entre Interiores", item: "/" },
                  { name: "Discografía", item: "/discografia" },
                  { name: display, item: `/discografia/${artist}` },
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
