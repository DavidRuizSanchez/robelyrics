import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import PublicFooter from "@/components/PublicFooter";
import PublicHeader from "@/components/PublicHeader";
import { ApiError, apiFetch } from "@/lib/api";
import { DESTACADOS, type Destacado } from "@/lib/enlaces";
import { estudioPorSlug } from "@/lib/estudios";
import type { PublicPostDetail } from "@/lib/types";

// La página del enlace de la bio de Instagram: lo que se promociona ahora mismo
// (`lib/enlaces.ts`) y, debajo, la puerta al resto de la web.
// Va fuera del sitemap y con noindex: es un índice de paso, no contenido.

const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL || "https://entreinteriores.com";

export const revalidate = 600;

export const metadata: Metadata = {
  title: "Enlaces · Entre Interiores",
  description:
    "Lo que estamos contando ahora en Instagram, con su página entera, y la puerta al resto de Entre Interiores.",
  alternates: { canonical: `${SITE_URL}/enlaces` },
  robots: { index: false, follow: true },
};

const FIJOS = [
  { href: "/", texto: "La web", nota: "Letras, discos y fichas de todo el universo Robe" },
  { href: "/blog", texto: "De manera urgente", nota: "Noticias, efemérides y memoria" },
  { href: "/registro", texto: "Crea tu cuenta gratis", nota: "Pregúntale al viento, Como lo diría Robe y más" },
];

type Tarjeta = {
  href: string;
  etiqueta: string;
  titulo: string;
  resumen: string | null;
  imagen: string | null;
  imagenAlt: string;
};

async function tarjeta(d: Destacado): Promise<Tarjeta | null> {
  if (d.tipo === "estudio") {
    const e = estudioPorSlug(d.slug);
    if (!e) return null;
    return {
      href: `/estudios/${e.slug}`, etiqueta: "Estudio", titulo: e.titulo,
      resumen: e.resumen, imagen: null, imagenAlt: "",
    };
  }
  try {
    const p = await apiFetch<PublicPostDetail>(`/public/posts/${d.slug}`, {
      authenticated: false,
    });
    return {
      href: `/blog/${p.slug}`, etiqueta: p.kind === "news" ? "Noticia" : "En el blog",
      titulo: p.title, resumen: p.excerpt, imagen: p.hero_image_url,
      imagenAlt: p.hero_image_alt || p.title,
    };
  } catch (e) {
    // Un post despublicado deja de promocionarse solo; cualquier otro fallo se
    // lanza para que el ISR conserve la versión anterior de la página.
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  }
}

export default async function EnlacesPage() {
  const destacados = (await Promise.all(DESTACADOS.map(tarjeta))).filter(
    (t): t is Tarjeta => t !== null,
  );

  return (
    <>
      <PublicHeader />
      <main className="px-4 md:px-14 py-10 md:py-14 max-w-[760px] mx-auto">
        <header className="mb-10">
          <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-3">
            desde instagram
          </p>
          <h1 className="font-serif text-5xl md:text-[64px] text-ink leading-[0.95] tracking-[-1.5px] m-0">
            Lo de la bio
          </h1>
          <p className="mt-5 font-serif italic text-lg md:text-xl text-ink-dim leading-relaxed">
            Lo que estamos contando ahora, con su página entera.
          </p>
        </header>

        <ul className="space-y-6 mb-14">
          {destacados.map((t) => (
            <li key={t.href}>
              <Link
                href={t.href}
                data-cursor="hover"
                className="group block border border-divider hover:border-accent transition-colors"
              >
                {t.imagen && (
                  // Entera y con sus proporciones: un cartel recortado pierde
                  // justo lo que dice (el del #65 es cuadrado y perdía el título).
                  <div className="overflow-hidden bg-divider">
                    <Image
                      src={t.imagen}
                      alt={t.imagenAlt}
                      width={1200}
                      height={1200}
                      sizes="(min-width: 768px) 760px, 100vw"
                      className="w-full h-auto transition-transform duration-300 group-hover:scale-[1.02]"
                    />
                  </div>
                )}
                <div className="px-5 py-5 md:px-7 md:py-6">
                  <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-2">
                    {t.etiqueta}
                  </p>
                  <h2 className="font-serif text-2xl md:text-[32px] text-ink group-hover:text-accent transition-colors leading-tight m-0">
                    {t.titulo}
                  </h2>
                  {t.resumen && (
                    <p className="mt-3 font-serif text-[17px] text-ink-dim leading-relaxed line-clamp-3">
                      {t.resumen}
                    </p>
                  )}
                  <p className="mt-4 font-mono text-[11px] tracking-[2px] uppercase text-accent">
                    Leer →
                  </p>
                </div>
              </Link>
            </li>
          ))}
        </ul>

        <nav aria-label="El resto de la web" className="pt-8 border-t border-divider">
          <p className="font-mono text-[10px] tracking-[3px] uppercase text-ink-dim mb-4">
            y además
          </p>
          <ul className="space-y-3">
            {FIJOS.map((f) => (
              <li key={f.href}>
                <Link
                  href={f.href}
                  data-cursor="hover"
                  className="group block border border-divider hover:border-accent px-5 py-4 transition-colors"
                >
                  <span className="block font-serif text-xl text-ink group-hover:text-accent transition-colors leading-tight">
                    {f.texto}
                  </span>
                  <span className="block mt-1 font-serif italic text-[15px] text-ink-dim leading-snug">
                    {f.nota}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      </main>
      <PublicFooter />
    </>
  );
}
