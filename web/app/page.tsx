import Link from "next/link";
import AlbumCover from "@/components/AlbumCover";
import HeaderImageBackdrop from "@/components/HeaderImageBackdrop";
import LogoBomba from "@/components/LogoBomba";
import PublicFooter from "@/components/PublicFooter";
import PublicHeader from "@/components/PublicHeader";
import { apiFetch } from "@/lib/api";
import { safeJsonLd } from "@/lib/safe-json-ld";
import {
  buildGraph,
  canonical,
  itemListNode,
  webPageNode,
} from "@/lib/schema-graph";
import type { PublicArtistDetail } from "@/lib/types";

export const metadata = {
  title: "Entre Interiores · Cancionero de Robe y Extremoduro",
  description:
    "Disco a disco, canción a canción: el universo de Robe y Extremoduro contado por sus letras y por la comunidad de fans.",
};

type SitemapEntry = {
  url_path: string;
  last_modified: string;
  entity_type: string;
};

export default async function PublicLandingPage() {
  // Cargar ambos artistas (Extremoduro y Robe) y la lista de URLs publicadas
  // para mostrar links reales a lo que ya está vivo. Si algo falla, fallback
  // suave a CTAs sin grid.
  const [extremoduro, robe, published, me] = await Promise.all([
    apiFetch<PublicArtistDetail>("/public/artists/extremoduro", {
      authenticated: false,
    }).catch(() => null),
    apiFetch<PublicArtistDetail>("/public/artists/robe", {
      authenticated: false,
    }).catch(() => null),
    apiFetch<SitemapEntry[]>("/public/sitemap-entries", {
      authenticated: false,
    }).catch(() => [] as SitemapEntry[]),
    apiFetch<{ id: number }>("/auth/me").catch(() => null),
  ]);
  const loggedIn = !!me;

  // Combinamos discos de ambos artistas etiquetando el artista para construir
  // hrefs correctos (`/{artist}/{album}`). Filtramos por url_path completo
  // contra el sitemap publicado, no por slug suelto, para evitar colisiones
  // si dos discos comparten slug entre artistas.
  const publishedAlbumPaths = new Set(
    published
      .filter((e) => e.entity_type === "album")
      .map((e) => e.url_path),
  );

  type AlbumWithArtist = PublicArtistDetail["albums"][number] & {
    artistSlug: string;
  };
  const allAlbums: AlbumWithArtist[] = [
    ...(extremoduro?.albums || []).map((a) => ({ ...a, artistSlug: "extremoduro" })),
    ...(robe?.albums || []).map((a) => ({ ...a, artistSlug: "robe" })),
  ];
  // Cronológico ascendente (1989 → presente) para que la historia se lea bien.
  allAlbums.sort((a, b) => (a.year ?? 0) - (b.year ?? 0));

  const albumsLive = allAlbums.filter((a) =>
    publishedAlbumPaths.has(`/${a.artistSlug}/${a.slug}`),
  );

  return (
    <div className="relative">
      <HeaderImageBackdrop
        src="/imagen-cabecera-tatuaje.png"
        height="1000px"
        opacity={0.15}
        position="center top"
      />
      <div className="relative z-10">
      <PublicHeader />
      <main className="px-5 md:px-14 max-w-[1100px] mx-auto">
        {/* Hero */}
        <section className="py-16 md:py-24 text-center">
          <div className="mb-8 flex flex-col items-center gap-4">
            <LogoBomba size={240} priority />
            <p className="font-mono text-[10px] tracking-[4px] uppercase text-accent">
              Entre Interiores
            </p>
          </div>
          <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-4">
            un cancionero íntimo
          </p>
          <h1 className="font-serif text-4xl md:text-6xl text-ink leading-[1.05] tracking-[-1px] mb-6">
            Robe y Extremoduro,
            <br />
            <span className="italic text-ink-dim">verso a verso</span>
          </h1>
          <p className="font-serif italic text-ink-dim text-lg md:text-xl leading-relaxed max-w-2xl mx-auto">
            Disco a disco, verso a verso. Lo que de verdad dicen estas canciones,
            contado por quien lleva media vida con ellas dentro.
          </p>

          <div className="flex flex-col sm:flex-row gap-3 justify-center pt-8">
            <Link
              href="/extremoduro"
              data-cursor="hover"
              className="border border-accent bg-accent text-white hover:bg-accent-bright font-mono text-[11px] tracking-[3px] uppercase px-7 py-3.5 transition-colors"
            >
              explorar Extremoduro →
            </Link>
            <Link
              href="/robe"
              data-cursor="hover"
              className="border border-accent text-accent hover:bg-accent hover:text-white font-mono text-[11px] tracking-[3px] uppercase px-7 py-3.5 transition-colors"
            >
              explorar Robe →
            </Link>
          </div>
        </section>

        {/* Discos publicados (capa pública SEO) */}
        {albumsLive.length > 0 && (
          <section className="py-12 border-t border-divider">
            <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-2">
              ya escrito
            </p>
            <h2 className="font-serif text-3xl md:text-4xl text-ink mb-8 leading-[1.15]">
              Discos con su análisis a tumba abierta
            </h2>
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-6 md:gap-8">
              {albumsLive.map((alb) => (
                <Link
                  key={`${alb.artistSlug}/${alb.slug}`}
                  href={`/${alb.artistSlug}/${alb.slug}`}
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
                  <p className="mt-3 font-serif text-[17px] text-ink leading-[1.25] transition-colors group-hover:text-accent">
                    {alb.title}
                  </p>
                  <p className="font-mono text-[10px] tracking-[2px] uppercase text-ink-faint mt-1">
                    {alb.year} · {alb.kind}
                  </p>
                </Link>
              ))}
            </div>
            <p className="mt-6 font-mono text-[10px] tracking-[1.5px] uppercase text-ink-faint">
              Lo que falta del catálogo va llegando poco a poco, con su análisis.
            </p>
          </section>
        )}

        {/* Pregúntale al viento (gancho de captación) */}
        <section className="py-16 border-t border-divider text-center">
          <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-3">
            nuevo · el viento responde
          </p>
          <h2 className="font-serif text-3xl md:text-5xl text-ink leading-[1.1] mb-4 tracking-[-1px]">
            Pregúntale al viento
          </h2>
          <p className="font-serif italic text-base md:text-lg text-ink-dim max-w-xl mx-auto mb-7">
            Las respuestas más auténticas a tus preguntas más introspectivas.
          </p>
          <ul className="flex flex-wrap gap-2 justify-center max-w-2xl mx-auto mb-8">
            {[
              "¿Qué es para ti la libertad?",
              "¿En qué año salió Agila?",
              "¿Qué piensas de la fama?",
              "¿De qué va «So payaso»?",
            ].map((q) => (
              <li
                key={q}
                className="font-serif italic text-ink-dim border border-divider rounded-full px-4 py-1.5 text-[15px]"
              >
                {q}
              </li>
            ))}
          </ul>
          <Link
            href="/biblioteca/consultorio"
            data-cursor="hover"
            className="inline-block border border-accent bg-accent text-white hover:bg-accent-bright font-mono text-[11px] tracking-[3px] uppercase px-7 py-3.5 transition-colors"
            title="Regístrate gratis para preguntarle"
          >
            pregúntale al viento →
          </Link>
          {!loggedIn && (
            <p className="mt-3 font-mono text-[10px] tracking-[1.5px] uppercase text-ink-faint">
              regístrate gratis para preguntar
            </p>
          )}
        </section>

        {/* CTA fan */}
        <section className="py-16 border-t border-divider text-center">
          <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-3">
            lo bueno, dentro
          </p>
          <h2 className="font-serif text-2xl md:text-3xl text-ink leading-[1.2] mb-4">
            Las canciones enteras, el buscador que te entiende y Robe contestándote
          </h2>
          <p className="font-serif italic text-ink-dim text-base md:text-lg max-w-xl mx-auto mb-6">
            {loggedIn
              ? "Ya estás dentro y es todo tuyo: las 144 canciones con la letra pegada al audio en directo y lo que los fans sacan de cada una, el buscador que te da el verso según lo que sientes y el sitio donde le preguntas a Robe y te responde con su voz."
              : "Hazte una cuenta gratis y entra a lo bueno: las 144 canciones con la letra pegada al audio en directo y lo que los fans sacan de cada una, el buscador que te da el verso según lo que sientes y el sitio donde le preguntas a Robe y te responde con su voz."}
          </p>
          <Link
            href={loggedIn ? "/biblioteca" : "/registro"}
            data-cursor="hover"
            className="inline-block border border-accent text-accent hover:bg-accent hover:text-white font-mono text-[11px] tracking-[3px] uppercase px-7 py-3.5 transition-colors"
          >
            {loggedIn ? "entrar a tu biblioteca" : "crear cuenta gratis"}
          </Link>
        </section>

        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: safeJsonLd(
              buildGraph([
                webPageNode({
                  path: "/",
                  name: "Entre Interiores · Cancionero de Robe y Extremoduro",
                  type: "CollectionPage",
                  mainEntityId: canonical.itemList("/"),
                  breadcrumb: false,
                }),
                itemListNode(
                  "/",
                  albumsLive.map((alb) => ({
                    name: alb.title,
                    url: `/${alb.artistSlug}/${alb.slug}`,
                    id: canonical.musicAlbum(alb.artistSlug, alb.slug),
                  })),
                ),
              ]),
            ),
          }}
        />
      </main>
      <PublicFooter />
      </div>
    </div>
  );
}
