import type { Metadata } from "next";
import Link from "next/link";
import Breadcrumbs from "@/components/Breadcrumbs";
import PublicFooter from "@/components/PublicFooter";
import PublicHeader from "@/components/PublicHeader";
import { ESTUDIOS } from "@/lib/estudios";
import { safeJsonLd } from "@/lib/safe-json-ld";
import {
  breadcrumbListNode,
  buildGraph,
  canonical,
  itemListNode,
  webPageNode,
} from "@/lib/schema-graph";

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || "https://entreinteriores.com";

export const revalidate = 3600;

export const metadata: Metadata = {
  title: "Estudios de datos sobre Extremoduro y Robe · Entre Interiores",
  description:
    "Investigaciones propias con datos verificables sobre el universo Extremoduro y Robe: el repertorio en directo, los conciertos provincia a provincia y lo que dicen las letras cuando se cuentan.",
  alternates: { canonical: `${SITE_URL}/estudios` },
};

export default function EstudiosPage() {
  return (
    <>
      <PublicHeader />
      <main className="px-5 md:px-14 py-10 md:py-14 max-w-[1100px] mx-auto">
        <Breadcrumbs
          className="mb-8"
          items={[
            { label: "Entre Interiores", href: "/" },
            { label: "Estudios", href: "/estudios" },
          ]}
        />

        <header className="mb-14">
          <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-2">
            datos propios
          </p>
          <h1 className="font-serif text-5xl md:text-[80px] text-ink leading-[0.95] tracking-[-2px] m-0">
            Estudios
          </h1>
          <p className="font-serif italic text-ink-dim text-lg mt-6 max-w-2xl leading-relaxed">
            Investigaciones hechas aquí, cifra a cifra, sobre el universo Extremoduro y Robe.
            Cada una lleva su método, sus fuentes y lo que sus datos no pueden decir. Se pueden
            citar y enlazar.
          </p>
        </header>

        <ul className="flex flex-col gap-px bg-divider border border-divider">
          {ESTUDIOS.map((e) => (
            <li key={e.slug} className="bg-bg">
              <Link
                href={`/estudios/${e.slug}`}
                data-cursor="hover"
                className="group block p-6 md:p-9 hover:bg-paper transition-colors"
              >
                <p className="font-mono text-[9px] tracking-[2px] uppercase text-ink-faint mb-3">
                  {new Date(e.datePublished).toLocaleDateString("es-ES", {
                    day: "numeric",
                    month: "long",
                    year: "numeric",
                  })}
                </p>
                <h2 className="font-serif text-2xl md:text-3xl text-ink group-hover:text-accent transition-colors leading-tight m-0">
                  {e.titulo}
                </h2>
                <p className="font-serif text-ink-dim mt-4 leading-relaxed max-w-2xl">
                  {e.resumen}
                </p>
              </Link>
            </li>
          ))}
        </ul>

        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: safeJsonLd(
              buildGraph([
                webPageNode({
                  path: "/estudios",
                  name: "Estudios de datos sobre Extremoduro y Robe",
                  type: "CollectionPage",
                  mainEntityId: canonical.itemList("/estudios"),
                }),
                itemListNode(
                  "/estudios",
                  ESTUDIOS.map((e) => ({
                    name: e.titulo,
                    url: `/estudios/${e.slug}`,
                  })),
                ),
                breadcrumbListNode("/estudios", [
                  { name: "Entre Interiores", item: "/" },
                  { name: "Estudios", item: "/estudios" },
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
