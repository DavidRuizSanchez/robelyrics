"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ActionBar, Button, Card, Data, Details, EmptyState, StatusBadge } from "@/components/admin/ui";
import { CAMBIO_CAMPO, CAMBIO_SEVERIDAD, etiqueta } from "@/lib/admin/labels";

export type CambioItem = {
  id: number;
  path: string;
  campo: string;
  severidad: string;
  antes: string | null;
  despues: string | null;
  detalle: {
    salen?: string[];
    entran?: string[];
    n_salen?: number;
    n_entran?: number;
    cadena_antes?: [number, string][];
    cadena_despues?: [number, string][];
  };
  causa: string | null;
  detected_at: string | null;
  seen_at: string | null;
  revertible: boolean;
};

const SITE = "https://entreinteriores.com";

function fecha(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("es-ES", {
    timeZone: "Europe/Madrid",
    dateStyle: "short",
    timeStyle: "short",
  });
}

function lista(titulo: string, items: string[] | undefined, total: number | undefined, tono: string) {
  if (!items || items.length === 0) return null;
  const resto = (total ?? items.length) - items.length;
  return (
    <div>
      <p className="text-xs text-ink-faint">{titulo}</p>
      <ul className={`mt-1 space-y-1 text-sm ${tono}`}>
        {items.map((x, i) => (
          <li key={i} className="break-words">
            {x}
          </li>
        ))}
      </ul>
      {resto > 0 && <p className="mt-1 text-xs text-ink-faint">y {resto} más</p>}
    </div>
  );
}

export default function CambiosLista({ items, vacio }: { items: CambioItem[]; vacio: string }) {
  const router = useRouter();
  const [vistos, setVistos] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState<number | "todos" | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function marcar(ids: number[], quien: number | "todos") {
    setBusy(quien);
    setErr(null);
    try {
      const res = await fetch("/biblioteca/admin/cambios/api/visto", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids }),
      });
      const data = (await res.json().catch(() => ({}))) as { error?: string };
      if (!res.ok) throw new Error(data.error || "No se pudo guardar.");
      setVistos((prev) => new Set([...prev, ...ids]));
      router.refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "No se pudo guardar.");
    } finally {
      setBusy(null);
    }
  }

  const pendientes = items.filter((it) => !it.seen_at && !vistos.has(it.id));
  if (items.length === 0) return <EmptyState>{vacio}</EmptyState>;

  // Función de render, no componente: un componente definido aquí dentro se
  // remontaría en cada render.
  function renderItem(it: CambioItem) {
    const sev = etiqueta(CAMBIO_SEVERIDAD, it.severidad);
    const visto = Boolean(it.seen_at) || vistos.has(it.id);
    const d = it.detalle || {};
    const conLista = Boolean(d.salen?.length || d.entran?.length);
    return (
      <Card key={it.id} as="li" tone={visto ? "neutral" : sev.tone} className={visto ? "opacity-60" : undefined}>
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge tone={sev.tone} title={sev.hint}>
            {sev.label}
          </StatusBadge>
          <span className="font-semibold text-ink">{CAMBIO_CAMPO[it.campo] ?? it.campo}</span>
          <span className="text-ink-faint">en</span>
          <a href={`${SITE}${it.path}`} target="_blank" rel="noreferrer" className="hover:underline">
            <Data>{it.path}</Data>
          </a>
          <span className="ml-auto text-xs text-ink-faint">{fecha(it.detected_at)}</span>
        </div>

        <p className="mt-2 text-sm text-ink-dim">
          {it.causa ? (
            <>
              <span className="text-ink">Por qué: </span>
              {it.causa}.
            </>
          ) : (
            <>
              <span className="text-ink">Sin causa conocida:</span> el sistema no ha hecho nada en esta
              página desde la pasada anterior. Revísala.
            </>
          )}
        </p>

        {it.antes !== null || it.despues !== null ? (
          !conLista && (
            <div className="mt-3 grid gap-2 md:grid-cols-2 text-sm">
              <div>
                <p className="text-xs text-ink-faint">Antes</p>
                <p className="mt-1 break-words text-ink-dim line-through decoration-ink-faint/50">
                  {it.antes ?? "—"}
                </p>
              </div>
              <div>
                <p className="text-xs text-ink-faint">Ahora</p>
                <p className="mt-1 break-words text-ink">{it.despues ?? "—"}</p>
              </div>
            </div>
          )
        ) : null}

        {conLista && (
          <Details className="mt-3" summary="Qué sale y qué entra">
            <div className="grid gap-3 md:grid-cols-2">
              {lista("Sale", d.salen, d.n_salen, "text-ink-dim line-through decoration-ink-faint/50")}
              {lista("Entra", d.entran, d.n_entran, "text-ink")}
            </div>
          </Details>
        )}

        <ActionBar
          primary={
            !visto && (
              <Button
                variant="primary"
                size="sm"
                loading={busy === it.id}
                onClick={() => marcar([it.id], it.id)}
              >
                Marcar como visto
              </Button>
            )
          }
          secondary={
            <>
              <a
                href={`${SITE}${it.path}`}
                target="_blank"
                rel="noreferrer"
                className="text-sm text-ink-dim hover:text-ink px-2 py-1"
              >
                Abrir la página
              </a>
              {it.revertible && (
                <a
                  href="/biblioteca/admin/seo/oportunidades"
                  className="text-sm text-ink-dim hover:text-ink px-2 py-1"
                  title="Esta página tiene una revisión guardada: se puede deshacer desde Oportunidades SEO."
                >
                  Deshacer desde Oportunidades SEO
                </a>
              )}
            </>
          }
        />
      </Card>
    );
  }

  return (
    <div className="space-y-3">
      {pendientes.length > 1 && (
        <div className="flex justify-end">
          <Button
            size="sm"
            loading={busy === "todos"}
            onClick={() => marcar(pendientes.map((it) => it.id), "todos")}
          >
            Marcar los {pendientes.length} como vistos
          </Button>
        </div>
      )}
      {err && <p className="text-sm text-danger">{err}</p>}
      <ul className="space-y-3">{items.map(renderItem)}</ul>
    </div>
  );
}
