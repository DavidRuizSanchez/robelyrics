"use client";

import { useState } from "react";

type Result =
  | { ok: true; proposal_id: number; title: string; rewritten: boolean; warning: string | null }
  | { ok: false; error: string };

export default function UrlIngestForm() {
  const [url, setUrl] = useState("");
  const [topic, setTopic] = useState("");
  const [rewrite, setRewrite] = useState(true);
  const [force, setForce] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Result | null>(null);

  async function submit() {
    const clean = url.trim();
    if (!clean) return;
    setBusy(true);
    setResult(null);
    try {
      const res = await fetch("/biblioteca/admin/blog/api/ingest-url", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: clean,
          topic: topic.trim() || undefined,
          rewrite,
          force,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setResult({ ok: false, error: data.error || `Error ${res.status}` });
      } else {
        setResult({ ok: true, ...data });
        setUrl("");
        setTopic("");
        setForce(false);
      }
    } catch (e) {
      setResult({ ok: false, error: String(e) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <details className="border border-divider mt-8">
      <summary
        data-cursor="hover"
        className="cursor-pointer select-none px-5 py-3 font-mono text-[10px] tracking-[2.5px] uppercase text-accent"
      >
        + añadir al banco desde una URL
      </summary>

      <div className="px-5 pb-6 pt-2 space-y-5 border-t border-divider">
        <p className="font-serif italic text-ink-dim text-sm">
          Pega un enlace y entra en «por validar» como una noticia más. Con la
          reescritura editorial investiga, escribe con nuestra voz y verifica los
          datos (tarda 1-2 min); sin ella, guarda el texto tal cual.
        </p>

        <div>
          <label
            htmlFor="ingest-url"
            className="block font-mono text-[10px] tracking-[2px] uppercase text-ink-dim mb-1.5"
          >
            URL del artículo *
          </label>
          <input
            id="ingest-url"
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://..."
            className="w-full bg-transparent border-0 border-b border-divider focus:border-accent focus:outline-none px-0 py-2 font-serif text-base text-ink"
          />
        </div>

        <div>
          <label
            htmlFor="ingest-topic"
            className="block font-mono text-[10px] tracking-[2px] uppercase text-ink-dim mb-1.5"
          >
            Tema (opcional)
          </label>
          <input
            id="ingest-topic"
            type="text"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="Pista del protagonista si el título no basta"
            className="w-full bg-transparent border-0 border-b border-divider focus:border-accent focus:outline-none px-0 py-2 font-serif text-base text-ink"
          />
        </div>

        <div className="flex flex-wrap items-center gap-6">
          <label className="flex items-center gap-2 font-mono text-[11px] tracking-[1px] text-ink-dim" data-cursor="hover">
            <input
              type="checkbox"
              checked={rewrite}
              onChange={(e) => setRewrite(e.target.checked)}
              className="accent-accent w-4 h-4"
            />
            reescribir con voz editorial
          </label>
          <label className="flex items-center gap-2 font-mono text-[11px] tracking-[1px] text-ink-dim" data-cursor="hover">
            <input
              type="checkbox"
              checked={force}
              onChange={(e) => setForce(e.target.checked)}
              className="accent-accent w-4 h-4"
            />
            forzar (saltar dedup de tema)
          </label>
        </div>

        <button
          type="button"
          onClick={submit}
          disabled={busy || !url.trim()}
          data-cursor="hover"
          className="border border-accent text-accent hover:bg-accent hover:text-white disabled:opacity-40 disabled:cursor-wait font-mono text-[11px] tracking-[3px] uppercase px-7 py-3 transition-colors"
        >
          {busy
            ? rewrite
              ? "investigando y escribiendo…"
              : "añadiendo…"
            : "añadir al banco"}
        </button>

        {result && !result.ok && (
          <p className="text-accent font-mono text-xs tracking-[1px]">✗ {result.error}</p>
        )}

        {result && result.ok && (
          <div className="border border-accent/30 bg-accent/5 p-4 space-y-2">
            <p className="font-mono text-[10px] tracking-[2px] uppercase text-accent">
              ✓ propuesta #{result.proposal_id} creada
              {result.rewritten ? " · reescrita" : " · texto en crudo"}
            </p>
            <p className="font-serif text-base text-ink leading-snug">{result.title}</p>
            {result.warning && (
              <p className="font-mono text-[11px] tracking-[0.5px] text-accent">
                ⚠ {result.warning}
              </p>
            )}
            <button
              type="button"
              onClick={() => window.location.reload()}
              data-cursor="hover"
              className="font-mono text-[10px] tracking-[2px] uppercase border border-divider hover:border-accent hover:text-accent text-ink-dim px-3 py-1.5"
            >
              recargar para verla en «por validar»
            </button>
          </div>
        )}
      </div>
    </details>
  );
}
