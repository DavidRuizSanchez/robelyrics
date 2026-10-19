"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ActionBar, Button, Callout, Card, JobStatus, Notice, StatusBadge } from "@/components/admin/ui";
import { ERRATA_REPORTER, ERRATA_STATUS, ERRATA_TARGET, etiqueta } from "@/lib/admin/labels";

export type ErrataItem = {
  id: number;
  target_type: string;
  target_id: number | null;
  field: string | null;
  reported_wrong: string | null;
  suggested_right: string | null;
  reporter: string | null;
  note: string | null;
  status: string;
  created_at: string;
};

type FixResult = {
  action: string;
  message: string;
  applied: boolean;
  closed: boolean;
  detail: string | null;
  verdict: string | null;
  confidence: number | null;
  sources: string[];
};

// Los tipos que el Motor de Consenso sabe verificar contra fuentes.
const FIXABLE = new Set(["song_lyrics", "authorship", "catalog", "image"]);

export default function ErrataRow({ item }: { item: ErrataItem }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [fixing, setFixing] = useState(false);
  const [fix, setFix] = useState<FixResult | null>(null);
  const [done, setDone] = useState<string | null>(null);
  // Antes un fallo al resolver no decía nada: el botón volvía a su sitio y ya.
  const [err, setErr] = useState<string | null>(null);

  async function resolve(action: "applied" | "rejected") {
    setBusy(true);
    try {
      const res = await fetch(`/biblioteca/admin/erratas/api/${item.id}/resolve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action }),
      });
      if (!res.ok) throw new Error();
      setDone(action === "applied" ? "aplicada" : "rechazada");
      router.refresh();
    } catch {
      setErr("No se pudo guardar la decisión. Vuelve a intentarlo.");
      setBusy(false);
    }
  }

  async function autoFix() {
    setFixing(true);
    setFix(null);
    try {
      const res = await fetch(`/biblioteca/admin/erratas/api/${item.id}/fix`, { method: "POST" });
      const data = (await res.json()) as FixResult & { error?: string };
      if (!res.ok) throw new Error(data?.error || "");
      setFix(data);
      if (data.closed) {
        setDone(data.applied ? "arreglada por consenso" : "cerrada");
        router.refresh();
      }
    } catch {
      setFix({
        action: "error",
        message: "No se pudo contactar con el motor de consenso.",
        applied: false,
        closed: false,
        detail: null,
        verdict: null,
        confidence: null,
        sources: [],
      });
    } finally {
      setFixing(false);
    }
  }

  if (done) {
    return (
      <Card tone="ok">
        <p className="text-sm text-ink-dim">Errata #{item.id} {done}.</p>
      </Card>
    );
  }

  const fixable = FIXABLE.has(item.target_type);
  const st = etiqueta(ERRATA_STATUS, item.status);

  return (
    <Card tone={st.tone}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="text-sm text-ink-dim">
          <span className="font-medium text-ink">{ERRATA_TARGET[item.target_type] || item.target_type}</span>
          <span className="text-ink-faint">
            {" "}
            · elemento #{item.target_id ?? "?"} · avisó{" "}
            {item.reporter ? ERRATA_REPORTER[item.reporter] ?? item.reporter : "alguien anónimo"} el{" "}
            {new Date(item.created_at).toLocaleDateString("es-ES", { timeZone: "Europe/Madrid" })}
          </span>
        </p>
        <StatusBadge tone={st.tone}>{st.label}</StatusBadge>
      </div>

      <div className="mt-3 grid gap-2 md:grid-cols-2">
        {item.reported_wrong && (
          <div className="rounded border border-danger/30 bg-danger-bg p-2">
            <p className="text-xs text-danger mb-0.5">Lo que está mal</p>
            <p className="font-serif text-[15px] text-ink">{item.reported_wrong}</p>
          </div>
        )}
        {item.suggested_right && (
          <div className="rounded border border-ok/30 bg-ok-bg p-2">
            <p className="text-xs text-ok mb-0.5">Lo que debería decir</p>
            <p className="font-serif text-[15px] text-ink">{item.suggested_right}</p>
          </div>
        )}
      </div>
      {item.note && <p className="mt-2 font-serif italic text-[14px] text-ink-dim">«{item.note}»</p>}

      {fixing && (
        <div className="mt-3">
          <JobStatus label="Comprobando en fuentes externas" hint="tarda unos segundos" />
        </div>
      )}

      {fix && (
        <Callout
          tone={fix.action === "error" ? "danger" : fix.applied ? "ok" : "info"}
          className="mt-3"
          title={fix.message}
        >
          {fix.detail && (
            // whitespace-pre-line: el detalle trae pasos numerados y snippets YAML
            // en varias líneas; sin esto se aplastan en un párrafo ilegible.
            <p className="whitespace-pre-line">{fix.detail}</p>
          )}
          {(fix.verdict || fix.sources.length > 0) && (
            <p className="mt-1 text-xs text-ink-faint">
              {fix.verdict && <>Veredicto: {fix.verdict}</>}
              {fix.confidence !== null ? ` · confianza ${fix.confidence.toFixed(2)}` : ""}
              {fix.sources.length > 0 ? ` · fuentes: ${fix.sources.join(", ")}` : ""}
            </p>
          )}
        </Callout>
      )}

      {err && (
        <div className="mt-3">
          <Notice onClose={() => setErr(null)}>{err}</Notice>
        </div>
      )}

      <ActionBar
        primary={
          fixable ? (
            <Button
              variant="primary"
              onClick={autoFix}
              disabled={busy || fixing}
              loading={fixing}
              loadingLabel="Verificando…"
              title="Vuelve a comprobarla con las fuentes de ahora y aplica solo lo que esté corroborado"
            >
              Arreglar automáticamente
            </Button>
          ) : (
            <span className="text-sm text-ink-faint">Este tipo no se puede verificar solo: decide tú.</span>
          )
        }
        secondary={
          <Button size="sm" variant="ghost" onClick={() => resolve("applied")} disabled={busy || fixing}>
            Ya lo corregí a mano
          </Button>
        }
        danger={
          <Button variant="danger" onClick={() => resolve("rejected")} disabled={busy || fixing}>
            Rechazar
          </Button>
        }
      />
    </Card>
  );
}
