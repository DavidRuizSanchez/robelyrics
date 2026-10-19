"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { ActionBar, Button, Notice, cx, inputClass } from "@/components/admin/ui";

export default function ProposalActions({
  id,
  status,
}: {
  id: number;
  status: string;
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

  return (
    <div>
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
