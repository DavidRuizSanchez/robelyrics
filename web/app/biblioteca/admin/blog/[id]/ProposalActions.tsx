"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { ActionBar, Button, Callout, Notice, StatusBadge, cx, inputClass } from "@/components/admin/ui";

const FILTRO: Record<string, string> = {
  rigor: "el editor jefe",
  foco: "el filtro de foco",
  lyrics: "el filtro de citas de letra",
  facts: "la comprobación de hechos",
  completeness: "la completitud (Robe y su trayectoria)",
  fuentes: "la voz propia (nombra fuentes externas)",
};

export default function ProposalActions({
  id,
  status,
  veredicto = null,
  nota = null,
  motivos = [],
  bloquea = null,
  forzada = false,
  tieneBorrador = false,
}: {
  id: number;
  status: string;
  veredicto?: string | null;
  nota?: number | null;
  motivos?: string[];
  bloquea?: string | null;
  forzada?: boolean;
  tieneBorrador?: boolean;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [date, setDate] = useState("");
  const [error, setError] = useState<string | null>(null);
  const todayIso = new Date().toISOString().slice(0, 10);

  async function call(action: string, body?: Record<string, unknown>) {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/biblioteca/admin/blog/api/${action}/${id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: body ? JSON.stringify(body) : undefined,
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setError(data.error || `Error ${res.status}`);
        return;
      }
      router.push("/biblioteca/admin/blog");
      router.refresh();
    } catch (e) {
      setError(`Error de red: ${e}`);
    } finally {
      setBusy(false);
    }
  }

  // Programar con aviso de conflicto (ya programada / día o semana ocupados /
  // evento tarde): el backend devuelve 409; confirmamos y reenviamos replace.
  async function scheduleWithConfirm(chosen: string) {
    setBusy(true);
    setError(null);
    try {
      const send = (replace: boolean) =>
        fetch(`/biblioteca/admin/blog/api/schedule/${id}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ date: chosen, replace }),
        });
      let res = await send(false);
      if (res.status === 409) {
        const data = await res.json().catch(() => ({}));
        if (!window.confirm(`${data.error}\n\n¿Programar igualmente?`)) return;
        res = await send(true);
      }
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setError(data.error || `Error ${res.status}`);
        return;
      }
      router.push("/biblioteca/admin/blog");
      router.refresh();
    } catch (e) {
      setError(`Error de red: ${e}`);
    } finally {
      setBusy(false);
    }
  }

  const vivo = status === "proposed" || status === "approved" || status === "scheduled";
  const reescribible = (status === "approved" || status === "scheduled") && tieneBorrador;

  function reescribir() {
    const texto = window.prompt(
      "Nota para el redactor (opcional): qué contar, qué evitar…\nSe reescribe y se vuelve a juzgar en unos minutos.",
      "",
    );
    if (texto === null) return;
    call("redraft", { nota: texto });
  }

  return (
    <div>
      {veredicto === "retenida" && (
        <Callout
          tone="danger"
          className="mt-4"
          title={`Retenida: no pasa ${bloquea ? FILTRO[bloquea] ?? bloquea : "los filtros"}${nota != null ? ` (${nota}/100)` : ""}. Así no saldrá: reescríbela.`}
        >
          {motivos.length > 0 && (
            <ul className="list-disc pl-5 space-y-1">
              {motivos.slice(0, 4).map((m) => (
                <li key={m}>{m}</li>
              ))}
            </ul>
          )}
        </Callout>
      )}
      {veredicto === "para_tu_lectura" && !forzada && (
        <Callout
          tone="info"
          className="mt-4"
          title={`Lista para tu lectura: pasa todos los filtros y el editor jefe la deja en ${nota ?? "?"}/100. No sale sola.`}
        >
          {motivos.length > 0 && (
            <ul className="list-disc pl-5 space-y-1">
              {motivos.slice(0, 3).map((m) => (
                <li key={m}>{m}</li>
              ))}
            </ul>
          )}
        </Callout>
      )}
      {veredicto === "pasa" && (
        <p className="mt-4">
          <StatusBadge tone="ok">✓ Pasa los filtros{nota != null ? ` (${nota}/100)` : ""}</StatusBadge>
        </p>
      )}
      {(status === "approved" || status === "scheduled") && !tieneBorrador && (
        <p className="mt-4 text-sm text-ink-dim">Escribiéndose… se juzga sola al terminar (unos minutos).</p>
      )}
      {error && (
        <div className="mt-4">
          <Notice onClose={() => setError(null)}>{error}</Notice>
        </div>
      )}
      <ActionBar
        primary={
          <>
            {status === "proposed" && (
              <Button variant="primary" loading={busy} onClick={() => call("approve")}>
                Aprobar idea
              </Button>
            )}
            {status === "approved" && (
              <span className="flex flex-wrap items-center gap-2">
                <label htmlFor="fecha" className="sr-only">
                  Fecha de publicación
                </label>
                <input
                  id="fecha"
                  type="date"
                  min={todayIso}
                  value={date}
                  onChange={(e) => setDate(e.target.value)}
                  className={cx(inputClass, "w-auto font-mono")}
                />
                <Button
                  variant="primary"
                  loading={busy}
                  onClick={() =>
                    date ? scheduleWithConfirm(date) : setError("Elige una fecha primero.")
                  }
                >
                  Programar
                </Button>
              </span>
            )}
            {status === "scheduled" && (
              <Button loading={busy} onClick={() => call("unschedule")}>
                Quitar fecha
              </Button>
            )}
            {veredicto === "para_tu_lectura" && !forzada && (
              <Button variant="primary" loading={busy} onClick={() => call("force-publish")}>
                Publicar tal cual (lo he leído)
              </Button>
            )}
            {reescribible && (
              <Button loading={busy} onClick={reescribir}>
                Reescribir
              </Button>
            )}
            {status === "discarded" && (
              <Button variant="primary" loading={busy} onClick={() => call("restore")}>
                Recuperar idea
              </Button>
            )}
          </>
        }
        danger={
          vivo && (
            <Button
              variant="danger"
              disabled={busy}
              onClick={() => {
                if (window.confirm("¿Rechazar esta propuesta?")) call("discard");
              }}
            >
              Rechazar
            </Button>
          )
        }
      />
    </div>
  );
}
