"use client";

import Link from "next/link";
import { useState } from "react";
import {
  ActionBar,
  Button,
  Callout,
  Card,
  Notice,
  StatusBadge,
  buttonClass,
  cx,
  inputClass,
} from "@/components/admin/ui";
import { GATE_LABEL, POST_STATUS, etiqueta, kindLabel } from "@/lib/admin/labels";
import type { Tone } from "@/lib/admin/labels";

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
  review_blocked_by?: string | null;
  review_blocked_reason?: string | null;
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
  const [error, setError] = useState<{ id: number; msg: string } | null>(null);

  async function act(
    id: number,
    action: "publish" | "reject" | "unpublish" | "unschedule" | "schedule",
    body?: unknown,
  ) {
    setBusy(id);
    setError(null);
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
        setError({ id, msg: `Error ${res.status}: ${text}` });
        return;
      }
      window.location.reload();
    } catch (e) {
      setError({ id, msg: `Error de red: ${e}` });
    } finally {
      setBusy(null);
    }
  }

  if (items.length === 0) {
    return <p className="text-ink-faint">No hay entradas que coincidan con el filtro.</p>;
  }

  return (
    <ul className="space-y-3">
      {items.map((p) => {
        const st = etiqueta(POST_STATUS, p.status);
        const canPublish = p.status === "pending_review" || p.status === "approved" || p.status === "draft";
        const canReject = p.status === "pending_review" || p.status === "draft";
        const canUnpublish = p.status === "published";
        // Se puede dar fecha a lo que aún no ha salido. Lo ya programado se
        // cambia desprogramando primero, para no tener dos fechas compitiendo.
        const canSchedule =
          p.status === "pending_review" || p.status === "approved" || p.status === "draft";
        const bloqueada = !!p.review_blocked_reason;
        const tone: Tone = bloqueada ? "danger" : st.tone;
        return (
          <Card key={p.id} as="li" tone={tone}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-ink-dim">
                <span>{kindLabel(p.kind)}</span>
                <span className="text-ink-faint">· creada {formatDate(p.created_at)}</span>
                {p.published_at && (
                  <span className="text-ink-faint">· publicada {formatDate(p.published_at)}</span>
                )}
                {p.status === "scheduled" && p.scheduled_for && (
                  <span>
                    · sale el <b className="text-ink">{formatDate(p.scheduled_for)}</b>
                  </span>
                )}
              </p>
              <div className="flex flex-wrap gap-1.5">
                <StatusBadge tone={st.tone} title={st.hint}>
                  {st.label}
                </StatusBadge>
                {/* Los mismos días que dice el correo diario, para poder
                    emparejar «esperando 124 días» con esta fila. */}
                {!!p.days_waiting && (
                  <StatusBadge tone={p.stale ? "danger" : "neutral"}>
                    {p.stale ? "⚠ " : ""}Esperando {p.days_waiting} día{p.days_waiting === 1 ? "" : "s"}
                  </StatusBadge>
                )}
              </div>
            </div>
            <Link
              href={`/biblioteca/admin/posts/${p.id}`}
              className="mt-1 block font-serif text-xl md:text-2xl text-ink leading-tight hover:text-accent"
            >
              {p.title}
            </Link>
            {p.excerpt && (
              <p className="mt-2 font-serif italic text-ink-dim leading-relaxed max-w-[680px]">
                {p.excerpt}
              </p>
            )}
            {/* Por qué la frenó un gate. Programar y publicar vuelven a
                pasarlo al pulsar; si el MISMO gate la frena otra vez sin
                cambios en el cuerpo, se retira de la cola. */}
            {bloqueada && (
              <Callout
                tone="danger"
                className="mt-3"
                title={`${p.status === "rejected" ? "Retirada" : "Frenada"}${
                  p.review_blocked_by
                    ? ` por ${GATE_LABEL[p.review_blocked_by] ?? p.review_blocked_by}`
                    : ""
                }`}
              >
                {p.review_blocked_reason}
                <p className="mt-1 text-xs text-ink-faint">
                  Publicar o programar vuelve a pasar el control: corrige el texto antes.
                </p>
              </Callout>
            )}
            {/* Fecha que quedó de una programación anterior: no publica
                nada (solo los `scheduled` entran al cron) pero confunde. */}
            {p.status !== "scheduled" && p.scheduled_for && (
              <p className="mt-2 text-xs text-ink-faint">
                Le queda una fecha antigua ({formatDate(p.scheduled_for)}) que no hace nada.
              </p>
            )}
            {p.source_url && p.source_name && (
              <p className="mt-2 text-sm text-ink-dim">
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
            {error?.id === p.id && (
              <div className="mt-3">
                <Notice onClose={() => setError(null)}>{error.msg}</Notice>
              </div>
            )}
            <ActionBar
              primary={
                <>
                  {canPublish && (
                    <Button
                      variant={bloqueada ? "secondary" : "primary"}
                      loading={busy === p.id}
                      onClick={() => act(p.id, "publish")}
                    >
                      Publicar ya
                    </Button>
                  )}
                  {/* Programar: publicar YA no siempre es lo que toca. El tope es
                      de 4 por semana, así que lo normal es repartir. */}
                  {canSchedule && (
                    <span className="flex items-center gap-1.5">
                      <input
                        type="date"
                        min={hoyISO()}
                        value={fechas[p.id] ?? ""}
                        onChange={(e) => setFechas((f) => ({ ...f, [p.id]: e.target.value }))}
                        aria-label={`Fecha para programar «${p.title}»`}
                        className={cx(inputClass, "w-auto font-mono")}
                      />
                      <Button
                        disabled={busy === p.id || !fechas[p.id]}
                        onClick={() => {
                          const cuando = fechas[p.id];
                          if (cuando) act(p.id, "schedule", { scheduled_for: cuando });
                        }}
                      >
                        Programar
                      </Button>
                    </span>
                  )}
                  {p.status === "scheduled" && (
                    <Button loading={busy === p.id} onClick={() => act(p.id, "unschedule")}>
                      Desprogramar
                    </Button>
                  )}
                </>
              }
              secondary={
                <>
                  <Link href={`/biblioteca/admin/posts/${p.id}`} className={buttonClass("ghost", "sm")}>
                    {bloqueada ? "Corregir →" : "Abrir y editar"}
                  </Link>
                  {p.status === "published" && (
                    <Link href={`/blog/${p.slug}`} target="_blank" className={buttonClass("ghost", "sm")}>
                      Ver en el blog ↗
                    </Link>
                  )}
                </>
              }
              danger={
                (canUnpublish || canReject) && (
                  <>
                    {canUnpublish && (
                      <Button
                        variant="danger"
                        disabled={busy === p.id}
                        onClick={() => act(p.id, "unpublish")}
                      >
                        Despublicar
                      </Button>
                    )}
                    {canReject && (
                      <Button
                        variant="danger"
                        disabled={busy === p.id}
                        onClick={() => {
                          if (window.confirm("¿Rechazar esta entrada?")) act(p.id, "reject");
                        }}
                      >
                        Rechazar
                      </Button>
                    )}
                  </>
                )
              }
            />
          </Card>
        );
      })}
    </ul>
  );
}
