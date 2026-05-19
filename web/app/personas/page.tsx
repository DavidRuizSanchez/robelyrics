import type { Metadata } from "next";
import Link from "next/link";
import Breadcrumbs from "@/components/Breadcrumbs";
import PublicFooter from "@/components/PublicFooter";
import PublicHeader from "@/components/PublicHeader";
import { apiFetch } from "@/lib/api";

const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL || "https://entreinteriores.com";

export const revalidate = 3600;

export const metadata: Metadata = {
  title: "Personas · Entre Interiores",
  description:
    "Las personas del universo Robe y Extremoduro: miembros históricos, colaboradores y voces amigas.",
  alternates: { canonical: `${SITE_URL}/personas` },
};

type PersonListItem = {
  slug: string;
  full_name: string;
  stage_name: string | null;
  birth_date: string | null;
  death_date: string | null;
  image_url: string | null;
};

function formatYear(iso: string | null): string | null {
  if (!iso) return null;
  return iso.slice(0, 4);
}

export default async function PersonasPage() {
  let items: PersonListItem[] = [];
  try {
    items = await apiFetch<PersonListItem[]>("/public/persons", {
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
            { label: "Personas", href: "/personas" },
          ]}
        />

        <header className="mb-14">
          <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-2">
            las personas
          </p>
          <h1 className="font-serif text-5xl md:text-[80px] text-ink leading-[0.95] tracking-[-2px] m-0">
            Quiénes
          </h1>
          <p className="font-serif italic text-ink-dim text-lg mt-6 max-w-2xl leading-relaxed">
            Robe y los demás. Los miembros que pasaron por Extremoduro y la
            banda solista, las voces amigas que el escenario y los discos
            cruzaron con la suya.
          </p>
        </header>

        {items.length === 0 ? (
          <p className="font-serif italic text-ink-dim">
            Sin personas registradas todavía.
          </p>
        ) : (
          <ul className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-8 gap-y-12">
            {items.map((p) => {
              const yearBirth = formatYear(p.birth_date);
              const yearDeath = formatYear(p.death_date);
              const years = yearBirth
                ? `${yearBirth}${yearDeath ? `–${yearDeath}` : "–"}`
                : "";
              return (
                <li key={p.slug}>
                  <Link
                    href={`/personas/${p.slug}`}
                    data-cursor="hover"
                    className="group block"
                  >
                    <div className="aspect-[3/4] bg-divider/30 mb-4 overflow-hidden">
                      {p.image_url ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={p.image_url}
                          alt={p.full_name}
                          loading="lazy"
                          className="w-full h-full object-cover group-hover:scale-[1.02] transition-transform duration-500"
                        />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center font-mono text-[10px] uppercase tracking-[2px] text-ink-faint">
                          sin foto
                        </div>
                      )}
                    </div>
                    <h2 className="font-serif text-2xl text-ink group-hover:text-accent transition-colors leading-tight">
                      {p.stage_name && p.stage_name !== p.full_name
                        ? p.stage_name
                        : p.full_name}
                    </h2>
                    {p.stage_name && p.stage_name !== p.full_name && (
                      <p className="font-serif italic text-ink-dim text-sm mt-1">
                        {p.full_name}
                      </p>
                    )}
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
      </main>
      <PublicFooter />
    </>
  );
}
