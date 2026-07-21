"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

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

const TARGET_LABEL: Record<string, string> = {
  song_lyrics: "Letra",
  authorship: "Autoría",
  catalog: "Disco/año",
  interpretation: "Interpretación",
};

export default function ErrataRow({ item }: { item: ErrataItem }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string | null>(null);

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
      setBusy(false);
    }
  }

  if (done) {
    return (
      <div className="border-b border-divider/50 py-3 font-mono text-[10px] tracking-[1px] uppercase text-ink-faint">
        Errata #{item.id} {done}.
      </div>
    );
  }

  return (
    <div className="border-b border-divider/50 py-4 space-y-2">
      <div className="flex items-center gap-3 font-mono text-[10px] tracking-[2px] uppercase">
        <span className="text-accent">{TARGET_LABEL[item.target_type] || item.target_type}</span>
        <span className="text-ink-faint">
          {item.status} · #{item.target_id ?? "?"} · {item.reporter || "anónimo"}
        </span>
      </div>
      {item.reported_wrong && (
        <p className="font-serif text-[15px] text-ink">
          <span className="text-ink-faint">Mal: </span>
          {item.reported_wrong}
        </p>
      )}
      {item.suggested_right && (
        <p className="font-serif text-[15px] text-ink">
          <span className="text-ink-faint">Debería: </span>
          {item.suggested_right}
        </p>
      )}
      {item.note && <p className="font-serif italic text-[14px] text-ink-dim">{item.note}</p>}
      <div className="flex gap-3 pt-1">
        <button
          onClick={() => resolve("applied")}
          disabled={busy}
          data-cursor="hover"
          className="border border-accent text-accent hover:bg-accent hover:text-white disabled:opacity-50 font-mono text-[10px] tracking-[2px] uppercase px-3 py-1 transition-colors"
        >
          Marcar aplicada
        </button>
        <button
          onClick={() => resolve("rejected")}
          disabled={busy}
          data-cursor="hover"
          className="font-mono text-[10px] tracking-[1px] uppercase text-ink-faint hover:text-ink disabled:opacity-50"
        >
          Rechazar
        </button>
      </div>
    </div>
  );
}
