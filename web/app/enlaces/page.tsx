import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import PublicFooter from "@/components/PublicFooter";
import PublicHeader from "@/components/PublicHeader";
import { apiFetch } from "@/lib/api";
import type { PublicEnlaceBio } from "@/lib/types";

// La página del enlace de la bio de Instagram. Cada pie que dice «link en la bio»
// manda aquí, y aquí cada post lleva a la página de la que habla.
// Va fuera del sitemap y con noindex: es un índice de paso, no contenido.

const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL || "https://entreinteriores.com";

export const revalidate = 600;

export const metadata: Metadata = {
  title: "Enlaces · Entre Interiores",
  description:
    "Lo último que hemos publicado en Instagram, cada post con su página: la letra, el disco, el artículo.",
  alternates: { canonical: `${SITE_URL}/enlaces` },
  robots: { index: false, follow: true },
};

const FIJOS = [
  { href: "/", texto: "La web", nota: "Letras, discos y fichas de todo el universo Robe" },
  { href: "/blog", texto: "De manera urgente", nota: "Noticias, efemérides y memoria" },
  { href: "/estudios", texto: "Estudios", nota: "Piezas con datos propios" },
  { href: "/registro", texto: "Crea tu cuenta gratis", nota: "Pregúntale al viento, Como lo diría Robe y más" },
];

export default async function EnlacesPage() {
  // Sin try/catch, como /blog: si el API falla al regenerar, Next sirve la
  // versión anterior en vez de guardar la página vacía.
  const posts = await apiFetch<PublicEnlaceBio[]>("/public/instagram/enlaces", {
    authenticated: false,
  });

  return (
    <>
      <PublicHeader />
      <main className="px-4 md:px-14 py-10 md:py-14 max-w-[880px] mx-auto">
        <header className="mb-10">
          <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-3">
            desde instagram
          </p>
          <h1 className="font-serif text-5xl md:text-[64px] text-ink leading-[0.95] tracking-[-1.5px] m-0">
            Lo de la bio
          </h1>
          <p className="mt-5 font-serif italic text-lg md:text-xl text-ink-dim leading-relaxed max-w-[620px]">
            Busca la imagen que has visto en Instagram: cada una te lleva a su
            página, con la letra, el disco o el artículo entero.
          </p>
        </header>

        <nav aria-label="Enlaces principales" className="mb-14 grid grid-cols-1 sm:grid-cols-2 gap-3">
          {FIJOS.map((f) => (
            <Link
              key={f.href}
              href={f.href}
              data-cursor="hover"
              className="group block border border-divider hover:border-accent px-5 py-4 transition-colors"
            >
              <span className="block font-serif text-2xl text-ink group-hover:text-accent transition-colors leading-tight">
                {f.texto}
              </span>
              <span className="block mt-1 font-serif italic text-[15px] text-ink-dim leading-snug">
                {f.nota}
              </span>
            </Link>
          ))}
        </nav>

        <section aria-labelledby="ultimos" className="mb-14">
          <h2
            id="ultimos"
            className="font-mono text-[11px] tracking-[3px] uppercase text-accent mb-5"
          >
            Lo último en Instagram
          </h2>
          {posts.length === 0 ? (
            <p className="font-serif italic text-lg text-ink-dim">
              Todavía no hay nada por aquí. Vuelve pronto.
            </p>
          ) : (
            <ul className="grid grid-cols-2 md:grid-cols-3 gap-x-3 gap-y-6">
              {posts.map((p) => (
                <li key={p.id}>
                  <Link href={p.destino} data-cursor="hover" className="group block">
                    <div className="relative aspect-square overflow-hidden bg-divider">
                      {p.imagen && (
                        <Image
                          src={p.imagen}
                          alt={p.titulo}
                          fill
                          unoptimized
                          sizes="(min-width: 768px) 280px, 50vw"
                          className="object-cover transition-transform duration-300 group-hover:scale-[1.03]"
                        />
                      )}
                    </div>
                    <p className="mt-2 font-mono text-[10px] tracking-[2px] uppercase text-accent">
                      {p.etiqueta} →
                    </p>
                    <p className="mt-1 font-serif text-[15px] md:text-base text-ink group-hover:text-accent transition-colors leading-snug line-clamp-2">
                      {p.titulo}
                    </p>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      </main>
      <PublicFooter />
    </>
  );
}
