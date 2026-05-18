import Link from "next/link";
import type { PublicTaxonomyPill } from "@/lib/types";

const HUB_PATH: Record<PublicTaxonomyPill["kind"], string> = {
  theme: "/temas",
  place: "/lugares",
  concept: "/conceptos",
};

// Chips horizontales con los temas, lugares y conceptos asociados a una
// canción. Cada chip enlaza al hub correspondiente. Si no hay nada en
// ninguna de las 3 listas, el componente no renderiza nada.
export default function TaxonomyPills({
  themes,
  places,
  concepts,
}: {
  themes: PublicTaxonomyPill[];
  places: PublicTaxonomyPill[];
  concepts: PublicTaxonomyPill[];
}) {
  const groups: { label: string; items: PublicTaxonomyPill[] }[] = [];
  if (themes.length) groups.push({ label: "Temas", items: themes });
  if (places.length) groups.push({ label: "Lugares", items: places });
  if (concepts.length) groups.push({ label: "Símbolos", items: concepts });
  if (groups.length === 0) return null;

  return (
    <section className="mt-12 mb-4 space-y-5">
      {groups.map((g) => (
        <div key={g.label}>
          <p className="font-mono text-[10px] tracking-[3px] uppercase text-ink-faint mb-2">
            {g.label}
          </p>
          <ul className="flex flex-wrap gap-2">
            {g.items.map((it) => (
              <li key={`${it.kind}-${it.slug}`}>
                <Link
                  href={`${HUB_PATH[it.kind]}/${it.slug}`}
                  data-cursor="hover"
                  className="inline-block border border-divider hover:border-accent hover:text-accent text-ink-dim px-3 py-1.5 font-mono text-[11px] tracking-[1.5px] uppercase transition-colors"
                >
                  {it.name}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}
