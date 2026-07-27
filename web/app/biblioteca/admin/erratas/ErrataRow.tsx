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

const TARGET_LABEL: Record<string, string> = {
  song_lyrics: "Letra",
  authorship: "Autoría",
  catalog: "Disco/año",
  interpretation: "Interpretación",
  image: "Imagen",
};

// Los tipos que el Motor de Consenso sabe verificar contra fuentes.
const FIXABLE = new Set(["song_lyrics", "authorship", "catalog", "image"]);

export default function ErrataRow({ item }: { item: ErrataItem }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [fixing, setFixing] = useState(false);
  const [fix, setFix] = useState<FixResult | null>(null);
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
      <div className="border-b border-divider/50 py-3 font-mono text-[10px] tracking-[1px] uppercase text-ink-faint">
        Errata #{item.id} {done}.
      </div>
    );
  }

  const fixable = FIXABLE.has(item.target_type);

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

      {fix && (
        <div className="border-l-2 border-accent/40 pl-3 py-1 space-y-1">
          <p className="font-serif text-[14px] text-ink">{fix.message}</p>
          {fix.detail && (
            // whitespace-pre-line: el detalle trae pasos numerados y snippets YAML
            // en varias líneas; sin esto se aplastan en un párrafo ilegible.
            <p className="font-serif italic text-[13px] text-ink-dim whitespace-pre-line">
              {fix.detail}
            </p>
          )}
          {(fix.verdict || fix.sources.length > 0) && (
            <p className="font-mono text-[10px] tracking-[1px] uppercase text-ink-faint">
              {fix.verdict}
              {fix.confidence !== null ? ` · conf ${fix.confidence.toFixed(2)}` : ""}
              {fix.sources.length > 0 ? ` · ${fix.sources.join(" · ")}` : ""}
            </p>
          )}
        </div>
      )}

      <div className="flex items-center gap-3 pt-1">
        {fixable && (
          <button
            onClick={autoFix}
            disabled={busy || fixing}
            data-cursor="hover"
            className="border border-accent text-accent hover:bg-accent hover:text-white disabled:opacity-50 font-mono text-[10px] tracking-[2px] uppercase px-3 py-1 transition-colors"
          >
            {fixing ? "Verificando…" : "Arreglar"}
          </button>
        )}
        <button
          onClick={() => resolve("applied")}
          disabled={busy || fixing}
          data-cursor="hover"
          className="border border-divider text-ink-dim hover:text-ink hover:border-ink-dim disabled:opacity-50 font-mono text-[10px] tracking-[2px] uppercase px-3 py-1 transition-colors"
        >
          Marcar aplicada
        </button>
        <button
          onClick={() => resolve("rejected")}
          disabled={busy || fixing}
          data-cursor="hover"
          className="font-mono text-[10px] tracking-[1px] uppercase text-ink-faint hover:text-ink disabled:opacity-50"
        >
          Rechazar
        </button>
      </div>
      {fixing && (
        <p className="font-mono text-[10px] tracking-[1px] uppercase text-ink-faint">
          Consultando fuentes externas… esto tarda unos segundos.
        </p>
      )}
    </div>
  );
}
