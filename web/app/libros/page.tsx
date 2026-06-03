import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import Breadcrumbs from "@/components/Breadcrumbs";
import PublicFooter from "@/components/PublicFooter";
import PublicHeader from "@/components/PublicHeader";
import { apiFetch } from "@/lib/api";
import { safeJsonLd } from "@/lib/safe-json-ld";
import {
  breadcrumbListNode,
  buildGraph,
  canonical,
  itemListNode,
  webPageNode,
} from "@/lib/schema-graph";

const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL || "https://entreinteriores.com";

export const revalidate = 3600;

export const metadata: Metadata = {
  title: "Libros sobre Extremoduro y Robe · Entre Interiores",
  description:
    "La bibliografía del universo Extremoduro y Robe: la biografía autorizada De Profundis, Talento innato, Poesía básica, la única novela de Robe y más. Fichas, autores y dónde situar cada libro.",
  alternates: { canonical: `${SITE_URL}/libros` },
};

type BookListItem = {
  slug: string;
  title: string;
  subtitle: string | null;
  authors: string[];
  year: number | null;
  kind: string;
  availability: string;
  cover_url: string | null;
  summary: string | null;
};

const KIND_LABEL: Record<string, string> = {
  biografia: "biografía",
  ensayo: "ensayo",
  novela: "novela",
  monografico: "monográfico",
  poesia: "poesía",
};

export default async function LibrosPage() {
  let items: BookListItem[] = [];
  try {
    items = await apiFetch<BookListItem[]>("/public/books", {
      authenticated: false,
    });
  } catch {
    items = [];
  }

  return (
    <>
      <PublicHeader />
      <main className="px-5 md:px-14 py-10 md:py-14 max-w-[1100px] mx-auto">
        <Breadcrumbs
          className="mb-8"
          items={[
            { label: "Entre Interiores", href: "/" },
            { label: "Libros", href: "/libros" },
          ]}
        />

        <header className="mb-14">
          <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-2">
            la biblioteca
          </p>
          <h1 className="font-serif text-5xl md:text-[80px] text-ink leading-[0.95] tracking-[-2px] m-0">
            Libros
          </h1>
          <p className="font-serif italic text-ink-dim text-lg mt-6 max-w-2xl leading-relaxed">
            Todo lo que se ha escrito sobre el universo Extremoduro y Robe, y lo
            que escribió el propio Robe. Biografías, ensayos y la única novela
            del poeta de Plasencia.
          </p>
        </header>

        {items.length === 0 ? (
          <p className="font-serif italic text-ink-dim">
            Sin libros registrados todavía.
          </p>
        ) : (
          <ul className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-x-8 gap-y-12">
            {items.map((b) => (
              <li key={b.slug}>
                <Link
                  href={`/libros/${b.slug}`}
                  data-cursor="hover"
                  className="group block"
                >
                  <div className="aspect-[2/3] bg-divider/30 mb-4 overflow-hidden relative flex items-center justify-center border border-divider">
                    {b.cover_url ? (
                      <Image
                        src={b.cover_url}
                        alt={`Portada de «${b.title}»`}
                        fill
                        sizes="(max-width: 640px) 50vw, (max-width: 1024px) 33vw, 25vw"
                        className="object-cover group-hover:scale-[1.02] transition-transform duration-500"
                      />
                    ) : (
                      <span className="font-serif italic text-ink-dim text-center text-lg leading-tight px-4 select-none">
                        {b.title}
                      </span>
                    )}
                  </div>
                  <p className="font-mono text-[9px] tracking-[2px] uppercase text-accent mb-1">
                    {KIND_LABEL[b.kind] || b.kind}
                  </p>
                  <h2 className="font-serif text-xl text-ink group-hover:text-accent transition-colors leading-tight">
                    {b.title}
                  </h2>
                  {b.authors.length > 0 && (
                    <p className="font-mono text-[10px] tracking-[2px] uppercase text-ink-faint mt-2">
                      {b.authors.join(" · ")}
                      {b.year ? ` · ${b.year}` : ""}
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
                webPageNode({
                  path: "/libros",
                  name: "Libros sobre Extremoduro y Robe",
                  type: "CollectionPage",
                  mainEntityId: canonical.itemList("/libros"),
                }),
                itemListNode(
                  "/libros",
                  items.map((b) => ({
                    name: b.title,
                    url: `/libros/${b.slug}`,
                    id: canonical.book(b.slug),
                  })),
                ),
                breadcrumbListNode("/libros", [
                  { name: "Entre Interiores", item: "/" },
                  { name: "Libros", item: "/libros" },
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
