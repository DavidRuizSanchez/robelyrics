"use client";

import Link from "next/link";
import { Callout, EmptyState, StatusBadge } from "@/components/admin/ui";
import type { Tone } from "@/lib/admin/labels";

// Listado de SeoContent. La selección múltiple para publicar en bloque llamaba a
// una ruta inexistente (`seo/api/bulk`) y se ha retirado hasta decidir si se
// conecta a /admin/seo/bulk-publish, que publica sin controles.

export type SeoListItem = {
  id: number;
  entity_type: string;
  slug: string;
  entity_label: string;
  chars: number;
  generated_at: string;
  generated_by: string;
  reviewed_at: string | null;
  published: boolean;
};

const TIPO: Record<string, string> = {
  artist: "Artista",
  album: "Disco",
  song: "Canción",
  person: "Persona",
  band: "Grupo",
  theme: "Tema",
  place: "Lugar",
  concept: "Concepto",
  page: "Página",
};

function statusOf(item: SeoListItem): { label: string; tone: Tone } {
  if (item.published) return { label: "Publicada", tone: "ok" };
  if (item.reviewed_at) return { label: "Revisada, sin publicar", tone: "warn" };
  return { label: "Sin revisar", tone: "neutral" };
}

export default function SeoListWithBulk({ items }: { items: SeoListItem[] }) {
  if (items.length === 0) {
    return <EmptyState>No hay fichas que coincidan con el filtro.</EmptyState>;
  }

  return (
    <div className="space-y-3">
      {/* Publicar/despublicar en bloque: el botón llamaba a una ruta que no
          existe. El backend sí tiene /admin/seo/bulk-publish, pero publica SIN
          ningún control, así que activarlo es una decisión aparte (pendiente
          del OK de David). Mientras, se dice en vez de fallar en silencio. */}
      <Callout tone="neutral">
        Publicar o despublicar varias a la vez está desactivado de momento: abre cada ficha para
        hacerlo.
      </Callout>
      <ul className="divide-y divide-divider rounded-md border border-divider">
        {items.map((item) => {
          const st = statusOf(item);
          return (
            <li key={item.id}>
              <Link
                href={`/biblioteca/admin/seo/${item.id}`}
                className="flex flex-wrap items-center gap-3 px-4 py-3 hover:bg-paper group"
              >
                <span className="w-20 shrink-0 text-sm text-ink-faint">
                  {TIPO[item.entity_type] ?? item.entity_type}
                </span>
                <span className="flex-1 min-w-0">
                  <span className="block font-serif text-base md:text-lg text-ink group-hover:text-accent transition-colors truncate">
                    {item.entity_label}
                  </span>
                  <span className="block text-xs text-ink-faint">
                    {item.chars.toLocaleString("es-ES")} caracteres · generada{" "}
                    {new Date(item.generated_at).toLocaleDateString("es-ES")} ·{" "}
                    <span className="font-mono">{item.generated_by}</span>
                  </span>
                </span>
                <StatusBadge tone={st.tone}>{st.label}</StatusBadge>
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
