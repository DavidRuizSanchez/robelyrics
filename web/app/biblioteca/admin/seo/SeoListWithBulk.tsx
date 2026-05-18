"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

// Listado de SeoContent con selección múltiple + acciones de bulk publish/unpublish.
// Componente que faltaba del repo — reconstruido para destrabar build. Si en el
// futuro se necesita un flujo de bulk más rico (revisar masivamente, regenerar,
// etc.), extender desde aquí.

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

function statusLabel(item: SeoListItem): { label: string; cls: string } {
  if (item.published) return { label: "publicado", cls: "text-accent" };
  if (item.reviewed_at) return { label: "revisado", cls: "text-ink" };
  return { label: "sin revisar", cls: "text-ink-faint" };
}

export default function SeoListWithBulk({ items }: { items: SeoListItem[] }) {
  const [selected, setSelected] = useState<Set<number>>(new Set());

  const allOnPageIds = useMemo(() => items.map((i) => i.id), [items]);
  const allSelected =
    items.length > 0 && allOnPageIds.every((id) => selected.has(id));

  function toggle(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAll() {
    if (allSelected) {
      setSelected(new Set());
    } else {
      setSelected(new Set(allOnPageIds));
    }
  }

  async function bulk(action: "publish" | "unpublish") {
    if (selected.size === 0) return;
    const ids = Array.from(selected);
    const confirmed = window.confirm(
      `¿${action === "publish" ? "Publicar" : "Despublicar"} ${ids.length} entrada(s)?`,
    );
    if (!confirmed) return;
    try {
      const res = await fetch(`/biblioteca/admin/seo/api/bulk`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids, action }),
      });
      if (!res.ok) {
        const text = await res.text();
        alert(`Error ${res.status}: ${text}`);
        return;
      }
      window.location.reload();
    } catch (e) {
      alert(`Error de red: ${e}`);
    }
  }

  if (items.length === 0) {
    return (
      <p className="font-serif italic text-ink-dim text-lg mt-12">
        No hay entradas que coincidan con el filtro.
      </p>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4 font-mono text-[10px] tracking-[2px] uppercase">
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={allSelected}
            onChange={toggleAll}
            className="accent-accent"
          />
          <span className="text-ink-dim">
            {selected.size > 0
              ? `${selected.size} seleccionado${selected.size === 1 ? "" : "s"}`
              : "seleccionar todos"}
          </span>
        </label>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => bulk("publish")}
            disabled={selected.size === 0}
            data-cursor="hover"
            className="border border-divider hover:border-accent hover:text-accent text-ink-dim px-3 py-1.5 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            publicar
          </button>
          <button
            type="button"
            onClick={() => bulk("unpublish")}
            disabled={selected.size === 0}
            data-cursor="hover"
            className="border border-divider hover:border-accent hover:text-accent text-ink-dim px-3 py-1.5 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            despublicar
          </button>
        </div>
      </div>

      <ul className="divide-y divide-divider">
        {items.map((item) => {
          const st = statusLabel(item);
          return (
            <li key={item.id} className="flex items-center gap-4 py-3">
              <input
                type="checkbox"
                checked={selected.has(item.id)}
                onChange={() => toggle(item.id)}
                className="accent-accent shrink-0"
              />
              <Link
                href={`/biblioteca/admin/seo/${item.id}`}
                data-cursor="hover"
                className="flex-1 min-w-0 group"
              >
                <div className="flex items-baseline gap-3 flex-wrap">
                  <span className="font-mono text-[10px] tracking-[2px] uppercase text-ink-faint">
                    {item.entity_type}
                  </span>
                  <span className="font-serif text-base md:text-lg text-ink group-hover:text-accent transition-colors truncate">
                    {item.entity_label}
                  </span>
                </div>
                <p className="font-mono text-[10px] tracking-[1px] text-ink-faint mt-1">
                  {item.chars} chars · {item.generated_by} · {new Date(item.generated_at).toLocaleDateString("es-ES")}
                </p>
              </Link>
              <span className={`font-mono text-[10px] tracking-[2px] uppercase shrink-0 ${st.cls}`}>
                {st.label}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
