import type { Metadata } from "next";
import Link from "next/link";
import Breadcrumbs from "@/components/Breadcrumbs";
import NewsletterForm from "@/components/NewsletterForm";
import PublicFooter from "@/components/PublicFooter";
import PublicHeader from "@/components/PublicHeader";
import { apiFetch } from "@/lib/api";
import { safeJsonLd } from "@/lib/safe-json-ld";
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
          dangerouslySetInnerHTML={{ __html: safeJsonLd(jsonLd) }}
        />
      </main>
      <PublicFooter />
    </>
  );
}
