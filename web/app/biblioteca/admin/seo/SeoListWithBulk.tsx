"use client";

import Link from "next/link";
import { useState } from "react";
import { Button, EmptyState, Notice, StatusBadge } from "@/components/admin/ui";
import type { Tone } from "@/lib/admin/labels";

// Listado de SeoContent con selección múltiple para publicar o despublicar en
// bloque (proxy `seo/api/bulk` → /admin/seo/bulk-publish|unpublish). Publicar
// así hace lo mismo que el botón de cada ficha: la marca revisada y la publica.

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
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState<"publish" | "unpublish" | null>(null);
  const [aviso, setAviso] = useState<{ tone: "ok" | "danger"; msg: string } | null>(null);

  if (items.length === 0) {
    return <EmptyState>No hay fichas que coincidan con el filtro.</EmptyState>;
  }

  const todas = items.every((i) => selected.has(i.id));
  const elegidas = items.filter((i) => selected.has(i.id));
  const nPublicar = elegidas.filter((i) => !i.published).length;
  const nDespublicar = elegidas.filter((i) => i.published).length;

  function toggle(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function bulk(action: "publish" | "unpublish") {
    // Solo las que cambian de verdad: publicar algo ya publicado no hace nada.
    const ids = elegidas.filter((i) => (action === "publish" ? !i.published : i.published)).map((i) => i.id);
    if (ids.length === 0) return;
    const verbo = action === "publish" ? "Publicar" : "Despublicar";
    const aviso =
      action === "publish"
        ? "\n\nSalen en la web tal cual están, igual que con el botón de cada ficha."
        : "\n\nDejan de verse en la web hasta que las vuelvas a publicar.";
    if (!window.confirm(`¿${verbo} ${ids.length} ficha${ids.length === 1 ? "" : "s"}?${aviso}`)) return;
    setBusy(action);
    setAviso(null);
    try {
      const res = await fetch("/biblioteca/admin/seo/api/bulk", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids, action }),
      });
      const data = (await res.json().catch(() => ({}))) as { error?: string; updated?: number; skipped?: number[] };
      if (!res.ok) {
        setAviso({ tone: "danger", msg: data.error || `Error ${res.status}` });
        return;
      }
      window.location.reload();
    } catch (e) {
      setAviso({ tone: "danger", msg: `Error de red: ${e}` });
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-3">
      <div className="sticky top-24 z-20 flex flex-wrap items-center gap-3 rounded-md border border-divider bg-paper/95 px-4 py-2 backdrop-blur">
        <label className="flex items-center gap-2 text-sm text-ink-dim cursor-pointer">
          <input
            type="checkbox"
            checked={todas}
            onChange={() => setSelected(todas ? new Set() : new Set(items.map((i) => i.id)))}
            className="h-4 w-4 accent-accent"
          />
          {selected.size > 0
            ? `${elegidas.length} seleccionada${elegidas.length === 1 ? "" : "s"}`
            : "Seleccionar todas las de este filtro"}
        </label>
        <div className="flex flex-wrap gap-2 sm:ml-auto">
          <Button
            size="sm"
            variant="primary"
            disabled={busy !== null || nPublicar === 0}
            loading={busy === "publish"}
            loadingLabel="Publicando…"
            onClick={() => bulk("publish")}
          >
            Publicar ({nPublicar})
          </Button>
          <Button
            size="sm"
            variant="danger"
            disabled={busy !== null || nDespublicar === 0}
            loading={busy === "unpublish"}
            loadingLabel="Despublicando…"
            onClick={() => bulk("unpublish")}
          >
            Despublicar ({nDespublicar})
          </Button>
        </div>
      </div>
      {aviso && (
        <Notice tone={aviso.tone} onClose={() => setAviso(null)}>
          {aviso.msg}
        </Notice>
      )}
      <ul className="divide-y divide-divider rounded-md border border-divider">
        {items.map((item) => {
          const st = statusOf(item);
          return (
            <li key={item.id} className="flex items-center gap-3 px-4 py-3 hover:bg-paper">
              <input
                type="checkbox"
                checked={selected.has(item.id)}
                onChange={() => toggle(item.id)}
                aria-label={`Seleccionar ${item.entity_label}`}
                className="h-4 w-4 shrink-0 accent-accent"
              />
              <Link
                href={`/biblioteca/admin/seo/${item.id}`}
                className="flex flex-1 min-w-0 flex-wrap items-center gap-3 group"
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
                    {new Date(item.generated_at).toLocaleDateString("es-ES", { timeZone: "Europe/Madrid" })} ·{" "}
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
