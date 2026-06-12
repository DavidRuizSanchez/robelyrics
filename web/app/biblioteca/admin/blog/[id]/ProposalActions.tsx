"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

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
  const todayIso = new Date().toISOString().slice(0, 10);

  async function call(action: string, body?: Record<string, unknown>) {
    setBusy(true);
    try {
      const res = await fetch(`/biblioteca/admin/blog/api/${action}/${id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: body ? JSON.stringify(body) : undefined,
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        alert(data.error || `Error ${res.status}`);
        return;
      }
      router.push("/biblioteca/admin/blog");
      router.refresh();
    } catch (e) {
      alert(`Error de red: ${e}`);
    } finally {
      setBusy(false);
    }
  }

  const btn =
    "font-mono text-[10px] tracking-[2px] uppercase border px-3 py-1.5 disabled:opacity-40";
  const primary = `${btn} border-accent text-accent hover:bg-accent hover:text-white`;
  const ghost = `${btn} border-divider text-ink-dim hover:border-accent hover:text-accent`;
  const danger = `${btn} border-divider text-ink-faint hover:text-ink`;

  return (
    <div className="flex items-center gap-2 flex-wrap">
      {status === "proposed" && (
        <button type="button" disabled={busy} onClick={() => call("approve")} className={primary}>
          aprobar
        </button>
      )}
      {(status === "proposed" || status === "approved" || status === "scheduled") && (
        <button
          type="button"
          disabled={busy}
          onClick={() => {
            if (window.confirm("¿Rechazar esta propuesta?")) call("discard");
          }}
          className={danger}
        >
          rechazar
        </button>
      )}
      {status === "approved" && (
        <>
          <input
            type="date"
            min={todayIso}
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="bg-bg border border-divider text-ink font-mono text-[12px] px-2 py-1.5"
          />
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              date ? call("schedule", { date }) : alert("Elige una fecha primero")
            }
            className={primary}
          >
            programar
          </button>
        </>
      )}
      {status === "scheduled" && (
        <button type="button" disabled={busy} onClick={() => call("unschedule")} className={ghost}>
          quitar fecha
        </button>
      )}
      {status === "discarded" && (
        <button type="button" disabled={busy} onClick={() => call("restore")} className={primary}>
          recuperar
        </button>
      )}
    </div>
  );
}
