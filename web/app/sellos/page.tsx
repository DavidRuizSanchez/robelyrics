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
  title: "Sellos discográficos del universo Extremoduro · Entre Interiores",
  description:
    "Los sellos discográficos que editaron a Extremoduro y Robe: de El Dromedario Records a DRO, Avispa o Warner. La trastienda de la industria del rock estatal.",
  alternates: { canonical: `${SITE_URL}/sellos` },
};

type BandListItem = {
  slug: string;
  name: string;
  kind: string;
  founded_year: number | null;
  dissolved_year: number | null;
  image_url: string | null;
};

export default async function SellosPage() {
  let items: BandListItem[] = [];
  try {
    const all = await apiFetch<BandListItem[]>("/public/bands", {
      authenticated: false,
    });
    // /sellos solo lista sellos discográficos (kind === "label").
    items = all.filter((b) => b.kind === "label");
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
            { label: "Sellos", href: "/sellos" },
          ]}
        />

        <header className="mb-14">
          <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-2">
            la trastienda
          </p>
          <h1 className="font-serif text-5xl md:text-[80px] text-ink leading-[0.95] tracking-[-2px] m-0">
            Sellos discográficos
          </h1>
          <p className="font-serif italic text-ink-dim text-lg mt-6 max-w-2xl leading-relaxed">
            La trastienda del negocio: las discográficas que editaron y aguantaron
            a Extremoduro y Robe, de El Dromedario a Warner. ¿Buscas los{" "}
            <Link
              href="/grupos"
              data-cursor="hover"
              className="text-accent hover:underline not-italic"
            >
              grupos afines
            </Link>
            ?
          </p>
        </header>

        {items.length === 0 ? (
          <p className="font-serif italic text-ink-dim">
            Sin sellos registrados todavía.
          </p>
        ) : (
          <ul className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-8 gap-y-12">
            {items.map((b) => {
              const years = b.founded_year
                ? `${b.founded_year}${b.dissolved_year ? `–${b.dissolved_year}` : ""}`
                : "";
              return (
                <li key={b.slug}>
                  <Link
                    href={`/sellos/${b.slug}`}
                    data-cursor="hover"
                    className="group block"
                  >
                    <div className="aspect-[3/4] bg-divider/30 mb-4 overflow-hidden relative flex items-center justify-center">
                      {b.image_url ? (
                        <Image
                          src={b.image_url}
                          alt={`${b.name}, sello discográfico de Extremoduro y Robe`}
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
                      sello
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
                  path: "/sellos",
                  name: "Sellos discográficos del universo Extremoduro",
                  type: "CollectionPage",
                  mainEntityId: canonical.itemList("/sellos"),
                }),
                itemListNode(
                  "/sellos",
                  items.map((b) => ({
                    name: b.name,
                    url: `/sellos/${b.slug}`,
                    id: canonical.band(b.slug, true),
                  })),
                ),
                breadcrumbListNode("/sellos", [
                  { name: "Entre Interiores", item: "/" },
                  { name: "Sellos", item: "/sellos" },
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
