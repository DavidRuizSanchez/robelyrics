"use client";

import { useState } from "react";

type AdminSubscriberItem = {
  id: number;
  email: string;
  status: string;
  source: string | null;
  subscribed_at: string;
  confirmed_at: string | null;
  unsubscribed_at: string | null;
  last_sent_at: string | null;
};

const STATUS_LABEL: Record<string, { label: string; cls: string }> = {
  pending: { label: "pendiente", cls: "text-accent" },
  confirmed: { label: "confirmado", cls: "text-ink" },
  unsubscribed: { label: "baja", cls: "text-ink-faint" },
  bounced: { label: "rebotado", cls: "text-ink-faint" },
};

function fmt(iso: string | null): string {
  if (!iso) return "·";
  return new Date(iso).toLocaleDateString("es-ES", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export default function SubscriberListWithActions({
  items,
}: {
  items: AdminSubscriberItem[];
}) {
  const [busy, setBusy] = useState<number | null>(null);

  async function act(
    id: number,
    action: "resend-confirmation" | "mark-bounced" | "delete",
  ) {
    setBusy(id);
    try {
      const res = await fetch(`/biblioteca/admin/subscribers/api/${action}/${id}`, {
        method: "POST",
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
        No hay suscriptores con ese filtro.
      </p>
    );
  }

  return (
    <ul className="divide-y divide-divider">
      {items.map((s) => {
        const st = STATUS_LABEL[s.status] ?? { label: s.status, cls: "text-ink-faint" };
        const canResend = s.status === "pending";
        const canBounce = s.status !== "bounced" && s.status !== "unsubscribed";
        return (
          <li key={s.id} className="py-5">
            <div className="flex items-start justify-between gap-4 flex-wrap">
              <div className="flex-1 min-w-0">
                <p className="font-mono text-[12px] text-ink break-all">
                  {s.email}
                </p>
                <p className="mt-2 font-mono text-[10px] tracking-[1px] uppercase text-ink-faint">
                  alta {fmt(s.subscribed_at)}
                  {s.confirmed_at && ` · confirmó ${fmt(s.confirmed_at)}`}
                  {s.last_sent_at && ` · último envío ${fmt(s.last_sent_at)}`}
                  {s.source && ` · origen ${s.source}`}
                </p>
              </div>
              <div className="shrink-0 flex flex-col items-end gap-2">
                <span
                  className={`font-mono text-[10px] tracking-[2px] uppercase ${st.cls}`}
                >
                  {st.label}
                </span>
                <div className="flex gap-2 flex-wrap justify-end">
                  {canResend && (
                    <button
                      type="button"
                      onClick={() => act(s.id, "resend-confirmation")}
                      disabled={busy === s.id}
                      data-cursor="hover"
                      className="font-mono text-[10px] tracking-[2px] uppercase border border-accent text-accent hover:bg-accent hover:text-white px-3 py-1.5 disabled:opacity-40"
                    >
                      reenviar
                    </button>
                  )}
                  {canBounce && (
                    <button
                      type="button"
                      onClick={() => {
                        if (window.confirm("¿Marcar como rebotado?"))
                          act(s.id, "mark-bounced");
                      }}
                      disabled={busy === s.id}
                      data-cursor="hover"
                      className="font-mono text-[10px] tracking-[2px] uppercase border border-divider hover:border-accent hover:text-accent text-ink-dim px-3 py-1.5 disabled:opacity-40"
                    >
                      rebotado
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => {
                      if (
                        window.confirm(
                          `¿Borrar ${s.email}? Esto NO marca unsubscribe, borra el registro.`,
                        )
                      )
                        act(s.id, "delete");
                    }}
                    disabled={busy === s.id}
                    data-cursor="hover"
                    className="font-mono text-[10px] tracking-[2px] uppercase border border-divider hover:border-divider-strong text-ink-faint hover:text-ink px-3 py-1.5 disabled:opacity-40"
                  >
                    borrar
                  </button>
                </div>
              </div>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
