import type { Metadata } from "next";
import Link from "next/link";
import Breadcrumbs from "@/components/Breadcrumbs";
import NewsletterForm from "@/components/NewsletterForm";
import PublicFooter from "@/components/PublicFooter";
import PublicHeader from "@/components/PublicHeader";
import { apiFetch } from "@/lib/api";
import { safeJsonLd } from "@/lib/safe-json-ld";
import { asNode, breadcrumbListNode, buildGraph } from "@/lib/schema-graph";
import type { PublicPostListItem } from "@/lib/types";

const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL || "https://entreinteriores.com";

export const revalidate = 600;

export const metadata: Metadata = {
  title: "De manera urgente · Noticias y memoria de Robe y Extremoduro · Entre Interiores",
  description:
    "De manera urgente: noticias, efemérides y memoria sobre Robe y Extremoduro. Escrito desde el cariño y la admiración.",
  alternates: { canonical: `${SITE_URL}/blog` },
};

const KIND_LABEL: Record<string, string> = {
  editorial: "Editorial",
  news: "Noticia",
  anniversary: "Efeméride",
};

function formatDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("es-ES", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

export default async function BlogPage() {
  let posts: PublicPostListItem[] = [];
  try {
    posts = await apiFetch<PublicPostListItem[]>("/public/posts", {
      authenticated: false,
    });
  } catch {
    posts = [];
  }

  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "Blog",
    name: "Diario · Entre Interiores",
    url: `${SITE_URL}/blog`,
    isPartOf: { "@type": "WebSite", url: SITE_URL, name: "Entre Interiores" },
    author: { "@id": "https://davidruizsanchez.es/#person" },
    blogPost: posts.map((p) => ({
      "@type": "BlogPosting",
      headline: p.title,
      datePublished: p.published_at,
      url: `${SITE_URL}/blog/${p.slug}`,
      author: { "@id": "https://davidruizsanchez.es/#person" },
    })),
  };

  return (
    <>
      <PublicHeader />
      <main className="px-5 md:px-14 py-10 md:py-14 max-w-[1000px] mx-auto">
        <Breadcrumbs
          className="mb-8"
          items={[
            { label: "Entre Interiores", href: "/" },
            { label: "De manera urgente", href: "/blog" },
          ]}
        />

        <header className="mb-14">
          <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-3">
            bitácora · de manera urgente
          </p>
          <h1 className="font-serif text-5xl md:text-[72px] text-ink leading-[0.95] tracking-[-2px] m-0">
            De manera urgente
          </h1>
          <p className="mt-6 max-w-[640px] font-serif text-lg md:text-xl text-ink-dim leading-relaxed">
            Apuntes, noticias y efemérides sobre Robe y Extremoduro,
            escritos desde el cariño y la admiración. El nombre lo presta una
            canción de Robe: lo urgente no siempre es lo ruidoso.
          </p>
        </header>

        {/* Explainer: qué te llevas al registrarte (premium gratis) */}
        <section id="suscribete" className="scroll-mt-24 mb-12">
          <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-3">
            lo que te llevas
          </p>
          <h2 className="font-serif text-3xl md:text-[44px] text-ink leading-[1.05] tracking-[-1px] m-0">
            Hazte una cuenta gratis y entra a lo bueno
          </h2>
          <p className="mt-4 max-w-[640px] font-serif italic text-ink-dim text-lg leading-relaxed">
            Entre Interiores es gratis. Te registras y se te abre todo esto:
          </p>
          <div className="mt-8 grid grid-cols-1 sm:grid-cols-2 gap-x-10 gap-y-7">
            {[
              {
                t: "El diario en tu correo",
                d: "Te aviso cuando caiga algo nuevo por aquí. Ni spam ni rollos, te borras de un clic.",
              },
              {
                t: "Pregúntale al viento",
                d: "Le preguntas a Robe lo que quieras y te responde con su voz, hecha de sus entrevistas y sus letras.",
              },
              {
                t: "Como lo diría Robe",
                d: "Cuéntame cómo te sientes y te doy el verso del cancionero que lo dice por ti.",
              },
              {
                t: "Las canciones enteras",
                d: "Las 144, con la letra pegada al audio en directo para cantarlas sin perderte.",
              },
            ].map((f) => (
              <div key={f.t} className="border-t border-divider pt-4">
                <h3 className="font-serif text-xl text-ink leading-tight m-0">{f.t}</h3>
                <p className="font-serif italic text-ink-dim text-[15px] leading-relaxed mt-2">
                  {f.d}
                </p>
              </div>
            ))}
          </div>
        </section>

        <section className="mb-14 pb-10 border-b border-divider">
          <NewsletterForm source="blog" variant="block" />
        </section>

        {posts.length === 0 ? (
          <p className="font-serif italic text-lg text-ink-dim">
            Aún no hay entradas publicadas. Vuelve pronto.
          </p>
        ) : (
          <ul className="divide-y divide-divider">
            {posts.map((p) => (
              <li key={p.slug}>
                <Link
                  href={`/blog/${p.slug}`}
                  data-cursor="hover"
                  className="block py-8 group"
                >
                  <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-2">
                    {KIND_LABEL[p.kind] || p.kind} · {formatDate(p.published_at)}
                  </p>
                  <h2 className="font-serif text-2xl md:text-[34px] text-ink group-hover:text-accent transition-colors leading-tight">
                    {p.title}
                  </h2>
                  {p.excerpt && (
                    <p className="mt-3 font-serif text-lg text-ink-dim leading-relaxed max-w-[680px]">
                      {p.excerpt}
                    </p>
                  )}
                </Link>
              </li>
            ))}
          </ul>
        )}

        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: safeJsonLd(
              buildGraph([
                asNode(jsonLd),
                breadcrumbListNode("/blog", [
                  { name: "Entre Interiores", item: "/" },
                  { name: "De manera urgente", item: "/blog" },
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
