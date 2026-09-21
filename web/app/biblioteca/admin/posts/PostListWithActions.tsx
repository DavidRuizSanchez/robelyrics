"use client";

import Link from "next/link";
import { useState } from "react";

type AdminPostItem = {
  id: number;
  slug: string;
  kind: string;
  status: string;
  title: string;
  excerpt: string | null;
  source_url: string | null;
  source_name: string | null;
  created_at: string;
  published_at: string | null;
  scheduled_for: string | null;
  days_waiting?: number;
  stale?: boolean;
};

const KIND_LABEL: Record<string, string> = {
  editorial: "Editorial",
  news: "Noticia",
  anniversary: "Efeméride",
  "album-anniversary": "Aniversario de disco",
  spotlight: "Canción de la semana",
  evergreen: "Reportaje",
};

const STATUS_LABEL: Record<string, { label: string; cls: string }> = {
  draft: { label: "borrador", cls: "text-ink-faint" },
  pending_review: { label: "pendiente", cls: "text-accent" },
  approved: { label: "aprobado", cls: "text-ink" },
  scheduled: { label: "programado", cls: "text-ink" },
  published: { label: "publicado", cls: "text-accent" },
  rejected: { label: "rechazado", cls: "text-ink-faint" },
};

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("es-ES", {
    day: "numeric",
    month: "short",
    year: "numeric",
    // En UTC a propósito: el SSR corre en UTC y el navegador en hora local, así
    // que sin fijarla la misma fecha se pintaba distinta en cada lado.
    timeZone: "UTC",
  });
}

// Hoy en la zona del navegador (no en UTC): es la fecha que el usuario ve en el
// calendario del sistema, y es la que tiene que poder elegir como mínimo.
function hoyISO(): string {
  const ahora = new Date();
  return new Date(ahora.getTime() - ahora.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 10);
}

export default function PostListWithActions({ items }: { items: AdminPostItem[] }) {
  const [busy, setBusy] = useState<number | null>(null);
  // Fecha elegida por fila. Sin esto solo se podía publicar YA, y la única forma
  // de programar era entrar a la ficha de cada entrada de una en una.
  const [fechas, setFechas] = useState<Record<number, string>>({});

  async function act(
    id: number,
    action: "publish" | "reject" | "unpublish" | "unschedule" | "schedule",
    body?: unknown,
  ) {
    setBusy(id);
    try {
      const res = await fetch(`/biblioteca/admin/posts/api/${action}/${id}`, {
        method: "POST",
        // `schedule` lleva cuerpo; sin la cabecera el backend responde 422 y el
        // botón parecería roto sin decir por qué.
        ...(body !== undefined
          ? {
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(body),
            }
          : {}),
      });
      if (!res.ok) {
        const text = await res.text();
        alert(`Error ${res.status}: ${text}`);
        return;
      }
      window.location.reload();
    } catch (e) {
      alert(`Error de red: ${e}`);
    } finally {
      setBusy(null);
    }
  }

  if (items.length === 0) {
    return (
      <p className="font-serif italic text-ink-dim text-lg mt-6">
        No hay entradas que coincidan con el filtro.
      </p>
    );
  }

  return (
    <ul className="divide-y divide-divider">
      {items.map((p) => {
        const st = STATUS_LABEL[p.status] ?? { label: p.status, cls: "text-ink-faint" };
        const canPublish = p.status === "pending_review" || p.status === "approved" || p.status === "draft";
        const canReject = p.status === "pending_review" || p.status === "draft";
        const canUnpublish = p.status === "published";
        // Se puede dar fecha a lo que aún no ha salido. Lo ya programado se
        // cambia desprogramando primero, para no tener dos fechas compitiendo.
        const canSchedule =
          p.status === "pending_review" || p.status === "approved" || p.status === "draft";
        return (
          <li key={p.id} className="py-5">
            <div className="flex items-start justify-between gap-4 flex-wrap">
              <div className="flex-1 min-w-0">
                <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-1">
                  {KIND_LABEL[p.kind] || p.kind} · creado {formatDate(p.created_at)}
                  {p.published_at && ` · publicado ${formatDate(p.published_at)}`}
                  {p.status === "scheduled" && p.scheduled_for &&
                    ` · programado ${formatDate(p.scheduled_for)}`}
                  {/* Los mismos días que dice el correo diario, para poder
                      emparejar «esperando 124 días» con esta fila. */}
                  {!!p.days_waiting && ` · esperando ${p.days_waiting} día${p.days_waiting === 1 ? "" : "s"}`}
                  {p.stale && (
                    <span className="text-accent"> · ⚠ se está pudriendo</span>
                  )}
                  {/* Fecha que quedó de una programación anterior: no publica
                      nada (solo los `scheduled` entran al cron) pero confunde. */}
                  {p.status !== "scheduled" && p.scheduled_for && (
                    <span className="text-ink-faint"> · fecha huérfana {formatDate(p.scheduled_for)}</span>
                  )}
                </p>
                <Link
                  href={`/biblioteca/admin/posts/${p.id}`}
                  data-cursor="hover"
                  className="font-serif text-xl md:text-2xl text-ink leading-tight hover:text-accent"
                >
                  {p.title}
                </Link>
                {p.excerpt && (
                  <p className="mt-2 font-serif italic text-ink-dim text-base leading-relaxed max-w-[680px]">
                    {p.excerpt}
                  </p>
                )}
                {p.source_url && p.source_name && (
                  <p className="mt-2 font-mono text-[10px] tracking-[1px] text-ink-faint">
                    Fuente:{" "}
                    <a
                      href={p.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-accent hover:underline"
                    >
                      {p.source_name} ↗
                    </a>
                  </p>
                )}
              </div>
              <div className="shrink-0 flex flex-col items-end gap-2">
                <span className={`font-mono text-[10px] tracking-[2px] uppercase ${st.cls}`}>
                  {st.label}
                </span>
                <div className="flex gap-2 flex-wrap justify-end">
                  <Link
                    href={`/biblioteca/admin/posts/${p.id}`}
                    data-cursor="hover"
                    className="font-mono text-[10px] tracking-[2px] uppercase border border-divider hover:border-accent hover:text-accent text-ink-dim px-3 py-1.5"
                  >
                    abrir
                  </Link>
                  {p.status === "published" && (
                    <Link
                      href={`/blog/${p.slug}`}
                      target="_blank"
                      data-cursor="hover"
                      className="font-mono text-[10px] tracking-[2px] uppercase border border-divider hover:border-accent hover:text-accent text-ink-dim px-3 py-1.5"
                    >
                      ver ↗
                    </Link>
                  )}
                  {p.status === "scheduled" && (
                    <button
                      type="button"
                      onClick={() => act(p.id, "unschedule")}
                      disabled={busy === p.id}
                      data-cursor="hover"
                      className="font-mono text-[10px] tracking-[2px] uppercase border border-divider hover:border-accent hover:text-accent text-ink-dim px-3 py-1.5 disabled:opacity-40"
                    >
                      desprogramar
                    </button>
                  )}
                  {/* Programar: publicar YA no siempre es lo que toca. El tope es
                      de 4 por semana, así que lo normal es repartir. */}
                  {canSchedule && (
                    <span className="flex gap-1.5 items-center">
                      <input
                        type="date"
                        min={hoyISO()}
                        value={fechas[p.id] ?? ""}
                        onChange={(e) =>
                          setFechas((f) => ({ ...f, [p.id]: e.target.value }))
                        }
                        aria-label={`Fecha para programar «${p.title}»`}
                        className="bg-bg border border-divider focus:border-accent outline-none text-ink font-mono text-[11px] px-2 py-1.5"
                      />
                      <button
                        type="button"
                        onClick={() => {
                          const cuando = fechas[p.id];
                          if (!cuando) {
                            alert("Elige antes una fecha.");
                            return;
                          }
                          act(p.id, "schedule", { scheduled_for: cuando });
                        }}
                        disabled={busy === p.id || !fechas[p.id]}
                        data-cursor="hover"
                        className="font-mono text-[10px] tracking-[2px] uppercase border border-divider hover:border-accent hover:text-accent text-ink-dim px-3 py-1.5 disabled:opacity-40"
                      >
                        programar
                      </button>
                    </span>
                  )}
                  {canPublish && (
                    <button
                      type="button"
                      onClick={() => act(p.id, "publish")}
                      disabled={busy === p.id}
                      data-cursor="hover"
                      className="font-mono text-[10px] tracking-[2px] uppercase border border-accent text-accent hover:bg-accent hover:text-white px-3 py-1.5 disabled:opacity-40"
                    >
                      publicar
                    </button>
                  )}
                  {canUnpublish && (
                    <button
                      type="button"
                      onClick={() => act(p.id, "unpublish")}
                      disabled={busy === p.id}
                      data-cursor="hover"
                      className="font-mono text-[10px] tracking-[2px] uppercase border border-divider hover:border-accent hover:text-accent text-ink-dim px-3 py-1.5 disabled:opacity-40"
                    >
                      despublicar
                    </button>
                  )}
                  {canReject && (
                    <button
                      type="button"
                      onClick={() => {
                        if (window.confirm("¿Rechazar esta entrada?")) act(p.id, "reject");
                      }}
                      disabled={busy === p.id}
                      data-cursor="hover"
                      className="font-mono text-[10px] tracking-[2px] uppercase border border-divider hover:border-divider-strong text-ink-faint hover:text-ink px-3 py-1.5 disabled:opacity-40"
                    >
                      rechazar
                    </button>
                  )}
                </div>
              </div>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
