import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { notFound } from "next/navigation";
import BookDataTable from "@/components/BookDataTable";
import Breadcrumbs from "@/components/Breadcrumbs";
import MarkdownArticle from "@/components/MarkdownArticle";
import PublicFooter from "@/components/PublicFooter";
import PublicHeader from "@/components/PublicHeader";
import { apiFetch, ApiError } from "@/lib/api";
import { safeJsonLd } from "@/lib/safe-json-ld";
import {
  bookNode,
  breadcrumbListNode,
  buildGraph,
  canonical,
  webPageNode,
} from "@/lib/schema-graph";

const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL || "https://entreinteriores.com";

export const revalidate = 3600;

type BookDetail = {
  slug: string;
  title: string;
  subtitle: string | null;
  authors: string[];
  year: number | null;
  kind: string;
  availability: string;
  cover_url: string | null;
  cover_attribution: string | null;
  summary: string | null;
  publisher: string | null;
  isbn: string | null;
  pages: number | null;
  language: string;
  body_md: string | null;
  buy_links: { store: string; url: string; label?: string }[];
  about: string[];
  meta_title: string | null;
  meta_description: string | null;
};

// Mapa slug-de-artista → nombre, para enlazar de vuelta al universo.
const ABOUT_LABEL: Record<string, string> = {
  extremoduro: "Extremoduro",
  robe: "Robe",
};

async function fetchBook(slug: string): Promise<BookDetail | null> {
  try {
    return await apiFetch<BookDetail>(`/public/books/${slug}`, {
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
  const detail = await fetchBook(slug);
  if (!detail) return {};
  const fullTitle = detail.subtitle
    ? `${detail.title}. ${detail.subtitle}`
    : detail.title;
  const title = detail.meta_title || `${fullTitle} · Entre Interiores`;
  const description =
    detail.meta_description ||
    detail.summary ||
    `Ficha de «${detail.title}», libro del universo de Extremoduro y Robe.`;
  return {
    title,
    description,
    alternates: { canonical: `${SITE_URL}/libros/${slug}` },
    openGraph: {
      title,
      description,
      type: "book",
      images: detail.cover_url ? [{ url: detail.cover_url }] : undefined,
    },
  };
}

export default async function LibroPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const detail = await fetchBook(slug);
  if (!detail) notFound();

  const path = `/libros/${detail.slug}`;
  const aboutIds = detail.about.map((s) => canonical.musicGroup(s));

  const jsonLd = buildGraph([
    bookNode({
      slug: detail.slug,
      title: detail.title,
      subtitle: detail.subtitle,
      authors: detail.authors,
      year: detail.year,
      publisher: detail.publisher,
      isbn: detail.isbn,
      pages: detail.pages,
      language: detail.language,
      coverUrl: detail.cover_url,
      summary: detail.summary,
      aboutIds,
    }),
    webPageNode({
      path,
      name: detail.title,
      type: "WebPage",
      description: detail.meta_description || detail.summary,
      mainEntityId: canonical.book(detail.slug),
    }),
    breadcrumbListNode(path, [
      { name: "Entre Interiores", item: "/" },
      { name: "Libros", item: "/libros" },
      { name: detail.title, item: path },
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
            { label: "Libros", href: "/libros" },
            { label: detail.title, href: path },
          ]}
        />

        <article>
          <header className="grid grid-cols-1 md:grid-cols-[260px_1fr] gap-10 mb-12">
            {detail.cover_url ? (
              <div>
                <div className="aspect-[2/3] overflow-hidden bg-divider/30 relative border border-divider">
                  <Image
                    src={detail.cover_url}
                    alt={`Portada de «${detail.title}»`}
                    fill
                    sizes="(max-width: 768px) 100vw, 260px"
                    priority
                    className="object-cover"
                  />
                </div>
                {detail.cover_attribution && (
                  <p className="font-mono text-[10px] tracking-[1px] text-ink-faint mt-2 leading-relaxed">
                    {detail.cover_attribution}
                  </p>
                )}
              </div>
            ) : (
              <div className="aspect-[2/3] overflow-hidden relative bg-divider/30 border border-divider flex items-center justify-center">
                <span className="font-serif italic text-ink-dim text-center text-xl leading-tight px-5 select-none">
                  {detail.title}
                </span>
              </div>
            )}

            <div>
              <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-2">
                libro{detail.year ? ` · ${detail.year}` : ""}
              </p>
              {/* H1 con el NOMBRE COMPLETO del libro (título + subtítulo dentro
                  del propio h1): relevancia SEO y cero canibalización con
                  /extremoduro o /robe. */}
              <h1 className="font-serif text-4xl md:text-[56px] text-ink leading-[0.98] tracking-[-1.5px] m-0">
                {detail.title}
                {detail.subtitle && (
                  <span className="block font-serif italic text-ink-dim text-2xl md:text-3xl mt-3 leading-snug tracking-normal">
                    {detail.subtitle}
                  </span>
                )}
              </h1>
              {detail.authors.length > 0 && (
                <p className="font-mono text-[11px] tracking-[2px] uppercase text-ink-faint mt-5">
                  {detail.authors.join(" · ")}
                </p>
              )}
              {detail.summary && (
                <p className="font-serif text-ink-dim text-lg mt-6 leading-relaxed">
                  {detail.summary}
                </p>
              )}

              {/* TODO afiliados: aquí irán los botones de compra (buy_links) +
                  el disclaimer de afiliación / web no oficial cuando se active
                  la monetización. De momento NO se renderiza nada. */}
            </div>
          </header>

          <BookDataTable
            detail={{
              authors: detail.authors,
              year: detail.year,
              publisher: detail.publisher,
              isbn: detail.isbn,
              pages: detail.pages,
              language: detail.language,
              kind: detail.kind,
              availability: detail.availability,
            }}
          />

          {detail.body_md && <MarkdownArticle markdown={detail.body_md} />}
        </article>

        {detail.about.length > 0 && (
          <section className="mt-16 pt-8 border-t border-divider">
            <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-4">
              en este libro
            </p>
            <ul className="flex flex-wrap gap-x-6 gap-y-2 font-serif text-lg">
              {detail.about.map((s) => (
                <li key={s}>
                  <Link
                    href={`/${s}`}
                    data-cursor="hover"
                    className="text-accent hover:underline"
                  >
                    {ABOUT_LABEL[s] || s}
                  </Link>
                </li>
              ))}
            </ul>
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
