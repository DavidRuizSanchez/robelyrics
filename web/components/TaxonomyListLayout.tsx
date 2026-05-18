import Link from "next/link";
import Breadcrumbs from "@/components/Breadcrumbs";
import PublicFooter from "@/components/PublicFooter";
import PublicHeader from "@/components/PublicHeader";
import { safeJsonLd } from "@/lib/safe-json-ld";
import type { PublicTaxonomyListItem } from "@/lib/types";

const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL || "https://entreinteriores.com";

// Layout reutilizable para las páginas índice de taxonomía (/temas, /lugares,
// /conceptos). Cada item enlaza al detalle. Si la lista llega vacía,
// renderizamos un mensaje editorial (no 404, porque la página es un hub).

type Props = {
  hubSlug: "temas" | "lugares" | "conceptos";
  hubLabel: string;
  hubTitle: string;
  hubLead: string;
  items: PublicTaxonomyListItem[];
};

export default function TaxonomyListLayout({
  hubSlug,
  hubLabel,
  hubTitle,
  hubLead,
  items,
}: Props) {
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "CollectionPage",
    name: hubTitle,
    url: `${SITE_URL}/${hubSlug}`,
    isPartOf: { "@type": "WebSite", url: SITE_URL, name: "Entre Interiores" },
    mainEntity: {
      "@type": "ItemList",
      itemListElement: items.map((it, i) => ({
        "@type": "ListItem",
        position: i + 1,
        url: `${SITE_URL}/${hubSlug}/${it.slug}`,
        name: it.name,
      })),
    },
  };

  return (
    <>
      <PublicHeader />
      <main className="px-5 md:px-14 py-10 md:py-14 max-w-[1100px] mx-auto">
        <Breadcrumbs
          className="mb-8"
          items={[
            { label: "Entre Interiores", href: "/" },
            { label: hubLabel, href: `/${hubSlug}` },
          ]}
        />

        <header className="mb-14">
          <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-3">
            explorar por
          </p>
          <h1 className="font-serif text-5xl md:text-[72px] text-ink leading-[0.95] tracking-[-2px] m-0">
            {hubTitle}
          </h1>
          <p className="mt-6 max-w-[640px] font-serif text-lg md:text-xl text-ink-dim leading-relaxed">
            {hubLead}
          </p>
        </header>

        {items.length === 0 ? (
          <p className="font-serif italic text-lg text-ink-dim">
            Todavía no hay entradas publicadas en esta sección. Vuelve pronto.
          </p>
        ) : (
          <ul className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-x-6 gap-y-2">
            {items.map((it) => (
              <li key={it.slug}>
                <Link
                  href={`/${hubSlug}/${it.slug}`}
                  data-cursor="hover"
                  className="group block py-4 border-b border-divider"
                >
                  <p className="font-serif text-xl md:text-2xl text-ink group-hover:text-accent transition-colors leading-tight">
                    {it.name}
                  </p>
                  <p className="font-mono text-[10px] tracking-[2px] uppercase text-ink-faint mt-1">
                    {it.song_count} canci{it.song_count === 1 ? "ón" : "ones"}
                  </p>
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
