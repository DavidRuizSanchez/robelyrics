"use client";

import { useState } from "react";
import { Button, Notice, StatusBadge, Table, cx, tdClass } from "@/components/admin/ui";
import { SUBSCRIBER_STATUS, etiqueta } from "@/lib/admin/labels";

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

function fmt(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("es-ES", {
    day: "numeric",
    month: "short",
    year: "numeric",
    // Zona fija: el SSR corre en UTC y el navegador en local, y sin esto la
    // misma fecha salía distinta en cada lado (error de hidratación).
    timeZone: "Europe/Madrid",
  });
}

export default function SubscriberListWithActions({
  items,
}: {
  items: AdminSubscriberItem[];
}) {
  const [busy, setBusy] = useState<number | null>(null);
  const [aviso, setAviso] = useState<{ tone: "ok" | "danger"; msg: string } | null>(null);

  async function act(
    id: number,
    action: "resend-confirmation" | "mark-bounced" | "delete",
    email?: string,
  ) {
    setBusy(id);
    setAviso(null);
    try {
      const res = await fetch(`/biblioteca/admin/subscribers/api/${action}/${id}`, {
        method: "POST",
      });
      if (!res.ok) {
        const text = await res.text();
        setAviso({ tone: "danger", msg: `Error ${res.status}: ${text}` });
        return;
      }
      if (action === "resend-confirmation") {
        // Reenviar no cambia el estado del suscriptor (sigue pending hasta
        // que confirme). Damos feedback explícito en vez de recargar.
        setAviso({
          tone: "ok",
          msg: `Confirmación reenviada a ${email}. Sigue «sin confirmar» hasta que pulse el enlace del correo.`,
        });
        return;
      }
      window.location.reload();
    } catch (e) {
      setAviso({ tone: "danger", msg: `Error de red: ${e}` });
    } finally {
      setBusy(null);
    }
  }

  if (items.length === 0) {
    return <p className="text-ink-faint">No hay suscriptores con ese filtro.</p>;
  }

  return (
    <div className="space-y-3">
      {aviso && (
        <Notice tone={aviso.tone} onClose={() => setAviso(null)}>
          {aviso.msg}
        </Notice>
      )}
      <Table head={["Correo", "Estado", "Alta", "Confirmó", "Último envío", "Origen", "Acciones"]}>
        {items.map((s) => {
          const st = etiqueta(SUBSCRIBER_STATUS, s.status);
          const canResend = s.status === "pending";
          const canBounce = s.status !== "bounced" && s.status !== "unsubscribed";
          return (
            <tr key={s.id}>
              <td className={cx(tdClass, "font-mono text-[13px] text-ink break-all")}>{s.email}</td>
              <td className={tdClass}>
                <StatusBadge tone={st.tone}>{st.label}</StatusBadge>
              </td>
              <td className={cx(tdClass, "whitespace-nowrap text-ink-dim")}>{fmt(s.subscribed_at)}</td>
              <td className={cx(tdClass, "whitespace-nowrap text-ink-dim")}>{fmt(s.confirmed_at)}</td>
              <td className={cx(tdClass, "whitespace-nowrap text-ink-dim")}>{fmt(s.last_sent_at)}</td>
              <td className={cx(tdClass, "text-ink-faint")}>{s.source ?? "—"}</td>
              <td className={tdClass}>
                <div className="flex flex-wrap gap-1.5">
                  {canResend && (
                    <Button size="sm" disabled={busy === s.id} onClick={() => act(s.id, "resend-confirmation", s.email)}>
                      Reenviar confirmación
                    </Button>
                  )}
                  {canBounce && (
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={busy === s.id}
                      onClick={() => {
                        if (window.confirm("¿Marcar como rebotado?")) act(s.id, "mark-bounced");
                      }}
                    >
                      Marcar que rebota
                    </Button>
                  )}
                  <Button
                    size="sm"
                    variant="danger"
                    disabled={busy === s.id}
                    onClick={() => {
                      if (window.confirm(`¿Borrar ${s.email}? Esto NO es darle de baja: borra el registro.`))
                        act(s.id, "delete");
                    }}
                  >
                    Borrar
                  </Button>
                </div>
              </td>
            </tr>
          );
        })}
      </Table>
    </div>
  );
}
