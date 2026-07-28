"use client";

import { useState } from "react";

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
      <p className="font-mono text-[9px] tracking-[1px] uppercase text-ink-faint">
        efeméride · sale el {publishOn}
      </p>
    );
  }

  return (
    <div>
      <label className="font-mono text-[9px] tracking-[2px] uppercase text-ink-faint">
        programar
      </label>
      <div className="mt-1 flex items-center gap-2 flex-wrap">
        <input
          type="datetime-local"
          value={valor}
          disabled={disabled || guardando}
          onChange={(e) => setValor(e.target.value)}
          className="bg-transparent border border-divider focus:border-accent outline-none text-ink text-xs font-mono px-2 py-1.5 [color-scheme:dark]"
        />
        <button
          type="button"
          disabled={disabled || guardando || !valor}
          onClick={() =>
            // El input da hora local sin zona; `new Date` la interpreta como
            // local y `toISOString` la pasa a UTC, que es lo que espera la API.
            enviar({ publish_at: new Date(valor).toISOString() })
          }
          data-cursor="hover"
          className="font-mono text-[10px] tracking-[2px] uppercase border border-accent text-accent hover:bg-accent hover:text-white px-3 py-1.5 disabled:opacity-40"
        >
          {guardando ? "…" : "programar"}
        </button>
        {publishAt && (
          <button
            type="button"
            disabled={disabled || guardando}
            onClick={() => {
              setValor("");
              enviar({ clear_publish_at: true });
            }}
            data-cursor="hover"
            className="font-mono text-[10px] tracking-[2px] uppercase border border-divider text-ink-dim hover:border-accent hover:text-accent px-3 py-1.5 disabled:opacity-40"
          >
            quitar
          </button>
        )}
      </div>

      {publishAt ? (
        <p className="mt-1.5 font-mono text-[9px] tracking-[1px] uppercase text-accent">
          programado · {formatoLargo(publishAt)}
        </p>
      ) : (
        <p className="mt-1.5 font-mono text-[9px] text-ink-faint leading-relaxed">
          Sin programar entra en el goteo por orden de cola.
        </p>
      )}
      {error && (
        <p className="mt-1 font-mono text-[9px] text-red-400">{error}</p>
      )}
    </div>
  );
}
