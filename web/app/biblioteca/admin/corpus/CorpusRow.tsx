"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ActionBar, Button, Card, Details, Notice, StatusBadge } from "@/components/admin/ui";
import { CORPUS_KIND, CORPUS_NIVEL, CORPUS_STATUS, etiqueta } from "@/lib/admin/labels";

export type CorpusItem = {
  id: number;
  video_id: string;
  url: string;
  title: string | null;
  channel: string | null;
  kind: string;
  status: string;
  nivel: string | null;
  voces: string[];
  motivos: string[];
  descubierto_por: string | null;
  duration_s: number | null;
  error: string | null;
  attempts: number;
  published_at: string | null;
  created_at: string | null;
  done_at: string | null;
};

type Accion = "aprobar" | "descartar" | "reintentar" | "retirar";

const HECHO: Record<Accion, string> = {
  aprobar: "aprobado: tu Mac lo transcribirá en su próxima pasada",
  descartar: "descartado: no volverá a proponerse",
  reintentar: "vuelve a la cola: tu Mac lo intentará otra vez",
  retirar: "retirado: ya no está en el corpus ni en la búsqueda",
};

const ORIGEN: Record<string, string> = {
  busqueda: "lo encontró la búsqueda",
  canal: "subida de un canal que se vigila",
  inventario: "inventario de entrevistas",
};

function fecha(iso: string | null): string | null {
  if (!iso) return null;
  return new Date(iso).toLocaleDateString("es-ES", { timeZone: "Europe/Madrid" });
}

export default function CorpusRow({ item }: { item: CorpusItem }) {
  const router = useRouter();
  const [busy, setBusy] = useState<Accion | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function decidir(accion: Accion) {
    if (
      accion === "retirar" &&
      !window.confirm("Se borra su transcripción del corpus y de la búsqueda. No se puede deshacer. ¿Retirarlo?")
    ) {
      return;
    }
    setBusy(accion);
    setErr(null);
    try {
      const res = await fetch(`/biblioteca/admin/corpus/api/${item.id}/${accion}`, { method: "POST" });
      const data = (await res.json().catch(() => ({}))) as { error?: string };
      if (!res.ok) throw new Error(data.error || "No se pudo guardar.");
      setDone(HECHO[accion]);
      router.refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "No se pudo guardar.");
      setBusy(null);
    }
  }

  if (done) {
    return (
      <Card tone="ok">
        <p className="text-sm text-ink-dim">«{item.title ?? item.video_id}» {done}.</p>
      </Card>
    );
  }

  const nivel = item.nivel ? etiqueta(CORPUS_NIVEL, item.nivel) : null;
  const st = etiqueta(CORPUS_STATUS, item.status);
  const minutos = item.duration_s ? Math.round(item.duration_s / 60) : null;
  const subido = fecha(item.published_at);

  return (
    <Card tone={item.status === "failed" ? "danger" : (nivel?.tone ?? st.tone)}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <a
            href={item.url}
            target="_blank"
            rel="noopener noreferrer"
            className="font-serif text-[17px] text-ink hover:underline"
          >
            {item.title ?? item.video_id}
          </a>
          <p className="mt-0.5 text-sm text-ink-faint">
            {item.channel ?? "canal desconocido"}
            {minutos !== null && ` · ${minutos} min`}
            {subido && ` · subido el ${subido}`}
            {item.descubierto_por && ` · ${ORIGEN[item.descubierto_por] ?? item.descubierto_por}`}
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {nivel && (
            <StatusBadge tone={nivel.tone} title={nivel.hint}>
              {nivel.label}
            </StatusBadge>
          )}
          {item.status !== "detected" && <StatusBadge tone={st.tone}>{st.label}</StatusBadge>}
        </div>
      </div>

      <p className="mt-2 text-sm text-ink-dim">
        Entraría como: <span className="text-ink">{CORPUS_KIND[item.kind] ?? item.kind}</span>
      </p>

      {item.motivos.length > 0 && (
        <Details summary="Por qué lo propone el sistema" className="mt-2">
          <ul className="list-disc pl-5 text-sm text-ink-dim space-y-0.5">
            {item.motivos.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        </Details>
      )}

      {item.status === "failed" && item.error && (
        <p className="mt-2 text-sm text-danger">
          Falló {item.attempts} {item.attempts === 1 ? "vez" : "veces"}: {item.error.slice(0, 300)}
        </p>
      )}

      {err && (
        <div className="mt-3">
          <Notice onClose={() => setErr(null)}>{err}</Notice>
        </div>
      )}

      {(item.status === "detected" || item.status === "failed") && (
        <ActionBar
          primary={
            item.status === "detected" ? (
              <Button variant="primary" onClick={() => decidir("aprobar")} loading={busy === "aprobar"}
                loadingLabel="Aprobando…" disabled={busy !== null}>
                Aprobar e ingerir
              </Button>
            ) : (
              <Button variant="primary" onClick={() => decidir("reintentar")} loading={busy === "reintentar"}
                loadingLabel="Reintentando…" disabled={busy !== null}>
                Reintentar
              </Button>
            )
          }
          danger={
            <Button variant="danger" onClick={() => decidir("descartar")} loading={busy === "descartar"}
              loadingLabel="Descartando…" disabled={busy !== null}>
              Descartar
            </Button>
          }
        />
      )}

      {item.status === "done" && (
        <ActionBar
          danger={
            <Button variant="danger" onClick={() => decidir("retirar")} loading={busy === "retirar"}
              loadingLabel="Retirando…" disabled={busy !== null}>
              Retirar del corpus
            </Button>
          }
        />
      )}
    </Card>
  );
}
