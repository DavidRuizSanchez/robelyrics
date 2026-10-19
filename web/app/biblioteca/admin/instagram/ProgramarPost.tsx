"use client";

import { useState } from "react";
import { Button, Notice, cx, inputClass } from "@/components/admin/ui";

/**
 * Selector de fecha y hora de publicación de un post.
 *
 * La cola tiene dos formas de fijar el momento:
 *   - `publish_on` (día suelto): lo pone el generador de efemérides. Aquí solo
 *     se muestra, no se toca.
 *   - `publish_at` (fecha + hora): esto. Programación a mano.
 *
 * El `datetime-local` del navegador trabaja en hora LOCAL del admin, y el
 * backend guarda en UTC; la conversión se hace aquí en los dos sentidos para
 * que quien programa vea siempre su hora, no la del servidor.
 */

type Props = {
  itemId: number;
  publishAt: string | null;
  publishOn: string | null;
  disabled?: boolean;
  onSaved: (nuevo: string | null) => void;
};

/** ISO en UTC → "YYYY-MM-DDTHH:mm" en hora local, que es lo que pide el input. */
function isoALocal(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

function formatoLargo(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString("es-ES", {
    weekday: "short", day: "numeric", month: "short",
    hour: "2-digit", minute: "2-digit",
  });
}

export default function ProgramarPost({
  itemId,
  publishAt,
  publishOn,
  disabled = false,
  onSaved,
}: Props) {
  const [valor, setValor] = useState(isoALocal(publishAt));
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function enviar(body: Record<string, unknown>) {
    setGuardando(true);
    setError(null);
    try {
      const res = await fetch(`/biblioteca/admin/instagram/api/queue/${itemId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const j = await res.json().catch(() => ({}));
        throw new Error(j.error ?? `error ${res.status}`);
      }
      const data = await res.json();
      onSaved(data.publish_at ?? null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "no se pudo guardar");
    } finally {
      setGuardando(false);
    }
  }

  // Una efeméride ya tiene su día atado al aniversario: no se reprograma.
  if (publishOn) {
    return (
      <p className="text-sm text-ink-dim">
        Efeméride: sale el <b className="text-ink">{publishOn}</b>, el día del aniversario.
      </p>
    );
  }

  return (
    <div>
      <label htmlFor={`prog-${itemId}`} className="text-sm font-medium text-ink-dim">
        Día y hora de publicación
      </label>
      <div className="mt-1 flex items-center gap-2 flex-wrap">
        <input
          id={`prog-${itemId}`}
          type="datetime-local"
          value={valor}
          disabled={disabled || guardando}
          onChange={(e) => setValor(e.target.value)}
          className={cx(inputClass, "w-auto font-mono [color-scheme:dark]")}
        />
        <Button
          size="sm"
          disabled={disabled || guardando || !valor}
          loading={guardando}
          onClick={() =>
            // El input da hora local sin zona; `new Date` la interpreta como
            // local y `toISOString` la pasa a UTC, que es lo que espera la API.
            enviar({ publish_at: new Date(valor).toISOString() })
          }
        >
          Programar
        </Button>
        {publishAt && (
          <Button
            size="sm"
            variant="ghost"
            disabled={disabled || guardando}
            onClick={() => {
              setValor("");
              enviar({ clear_publish_at: true });
            }}
          >
            Quitar fecha
          </Button>
        )}
      </div>

      {publishAt ? (
        <p className="mt-1.5 text-sm text-info">Programado: {formatoLargo(publishAt)}</p>
      ) : (
        <p className="mt-1.5 text-xs text-ink-faint">
          Sin fecha, sale cuando le toque en la cola.
        </p>
      )}
      {error && (
        <div className="mt-2">
          <Notice onClose={() => setError(null)}>{error}</Notice>
        </div>
      )}
    </div>
  );
}
