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
  title: "Grupos afines a Extremoduro · Entre Interiores",
  description:
    "Los grupos del mismo barro que Extremoduro y Robe: el rock estatal que compartió escenario, cartel y carretera con ellos.",
  alternates: { canonical: `${SITE_URL}/grupos` },
};

type BandListItem = {
  slug: string;
  name: string;
  kind: string;
  founded_year: number | null;
  dissolved_year: number | null;
  image_url: string | null;
};

export default async function GruposPage() {
  let items: BandListItem[] = [];
  try {
    const all = await apiFetch<BandListItem[]>("/public/bands", {
      authenticated: false,
    });
    // /grupos solo lista bandas; los sellos discográficos viven en /sellos.
    items = all.filter((b) => b.kind !== "label");
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
            { label: "Grupos", href: "/grupos" },
          ]}
        />

        <header className="mb-14">
          <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-2">
            el mismo barro
          </p>
          <h1 className="font-serif text-5xl md:text-[80px] text-ink leading-[0.95] tracking-[-2px] m-0">
            Grupos afines a Extremoduro y Robe
          </h1>
          <p className="font-serif italic text-ink-dim text-lg mt-6 max-w-2xl leading-relaxed">
            El rock estatal que compartió escenario, cartel y carretera con
            Extremoduro y Robe. Las bandas del mismo barro. ¿Buscas los{" "}
            <Link
              href="/sellos"
              data-cursor="hover"
              className="text-accent hover:underline not-italic"
            >
              sellos discográficos
            </Link>
            ?
          </p>
        </header>

        {items.length === 0 ? (
          <p className="font-serif italic text-ink-dim">
            Sin grupos registrados todavía.
          </p>
        ) : (
          <ul className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-8 gap-y-12">
            {items.map((b) => {
              const years = b.founded_year
                ? `${b.founded_year}${b.dissolved_year ? `–${b.dissolved_year}` : ""}`
                : "";
              const kindLabel = b.kind === "label" ? "sello" : "grupo";
              return (
                <li key={b.slug}>
                  <Link
                    href={`/grupos/${b.slug}`}
                    data-cursor="hover"
                    className="group block"
                  >
                    <div className="aspect-[3/4] bg-divider/30 mb-4 overflow-hidden relative flex items-center justify-center">
                      {b.image_url ? (
                        <Image
                          src={b.image_url}
                          alt={`${b.name}, ${kindLabel} afín a Extremoduro y Robe`}
                          fill
                          sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw"
                          className="object-cover group-hover:scale-[1.02] transition-transform duration-500"
                        />
                      ) : (
                        <span className="font-serif text-ink-faint text-5xl select-none">
                          {b.name.charAt(0)}
                        </span>
                      )}
                    </div>
                    <p className="font-mono text-[9px] tracking-[2px] uppercase text-accent mb-1">
                      {kindLabel}
                    </p>
                    <h2 className="font-serif text-2xl text-ink group-hover:text-accent transition-colors leading-tight">
                      {b.name}
                    </h2>
                    {years && (
                      <p className="font-mono text-[10px] tracking-[2px] uppercase text-ink-faint mt-2">
                        {years}
                      </p>
                    )}
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: safeJsonLd(
              buildGraph([
                webPageNode({
                  path: "/grupos",
                  name: "Grupos afines a Extremoduro",
                  type: "CollectionPage",
                  mainEntityId: canonical.itemList("/grupos"),
                }),
                itemListNode(
                  "/grupos",
                  items.map((b) => ({
                    name: b.name,
                    url: `/grupos/${b.slug}`,
                    id: canonical.band(b.slug, b.kind === "label"),
                  })),
                ),
                breadcrumbListNode("/grupos", [
                  { name: "Entre Interiores", item: "/" },
                  { name: "Grupos", item: "/grupos" },
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
