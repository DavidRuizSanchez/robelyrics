"use client";

import { useState, useTransition } from "react";
import { createSourceAction, processSourceAction, type SourceCreateResult } from "./actions";

type Tab = "text" | "url" | "youtube";

const KIND_OPTIONS = [
  { value: "manual", label: "Manual / pegado" },
  { value: "blog", label: "Blog" },
  { value: "forum", label: "Foro" },
  { value: "youtube_transcript", label: "Transcript YouTube" },
  { value: "youtube_comment", label: "Comentario YouTube" },
  { value: "genius_annotation", label: "Anotación Genius" },
  { value: "thesis", label: "Tesis / paper" },
  { value: "book", label: "Libro" },
];

export default function SourceForm() {
  const [tab, setTab] = useState<Tab>("text");
  const [result, setResult] = useState<SourceCreateResult | null>(null);
  const [processResult, setProcessResult] = useState<{ status: "idle" | "running" | "done" | "error"; message?: string; log?: string[] }>({ status: "idle" });
  const [isPending, startTransition] = useTransition();
  const [isProcessing, startProcess] = useTransition();

  function handleSubmit(formData: FormData) {
    formData.set("mode", tab);
    if (tab === "youtube") {
      formData.set("kind", formData.get("kind")?.toString() || "youtube_transcript");
    }
    startTransition(async () => {
      const r = await createSourceAction(formData);
      setResult(r);
      setProcessResult({ status: "idle" });
    });
  }

  function handleProcess() {
    if (!result || !result.ok) return;
    const sourceId = result.source_id;
    setProcessResult({ status: "running" });
    startProcess(async () => {
      const r = await processSourceAction(sourceId);
      if (r.ok) {
        setProcessResult({
          status: "done",
          message: `Procesadas ${r.processed_song_slugs.length} canciones`,
          log: r.log,
        });
      } else {
        setProcessResult({ status: "error", message: r.error });
      }
    });
  }

  return (
    <div className="space-y-8">
      <div className="flex gap-1 border-b border-divider">
        {(["text", "url", "youtube"] as Tab[]).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            data-cursor="hover"
            className={`px-5 py-2.5 font-mono text-[10px] tracking-[2.5px] uppercase transition-colors border-b-2 -mb-px ${
              tab === t
                ? "text-accent border-accent"
                : "text-ink-dim border-transparent hover:text-ink"
            }`}
          >
            {t === "text" ? "Texto pegado" : t === "url" ? "URL para scrape" : "YouTube"}
          </button>
        ))}
      </div>

      <form action={handleSubmit} className="space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          <Field label="URL canónica de la fuente *" name="url" placeholder="https://..." required />
          <SelectField label="Tipo (kind)" name="kind" options={KIND_OPTIONS} defaultValue={tab === "youtube" ? "youtube_transcript" : "manual"} />
          <Field label="Título" name="title" placeholder="Título del post / vídeo / fragmento" />
          <Field label="Autor" name="author" placeholder="Nombre del autor (opcional)" />
        </div>

        {tab === "text" && (
          <TextareaField
            label="Contenido"
            name="content"
            placeholder="Pega aquí el texto del análisis fan, comentario, hilo, etc."
            rows={10}
          />
        )}

        {tab === "url" && (
          <Field
            label="URL para scrape (si difiere de la canónica)"
            name="fetch_url"
            placeholder="https://..."
            hint="Si está vacío, se scrapeará la URL canónica de arriba."
          />
        )}

        {tab === "youtube" && (
          <Field
            label="URL del vídeo YouTube"
            name="youtube_url"
            placeholder="https://www.youtube.com/watch?v=..."
            hint="Se descargará el transcript en español si está disponible."
            required
          />
        )}

        <div className="flex items-center gap-4">
          <button
            type="submit"
            disabled={isPending}
            data-cursor="hover"
            className="border border-accent text-accent hover:bg-accent hover:text-white disabled:opacity-50 disabled:cursor-wait font-mono text-[11px] tracking-[3px] uppercase px-7 py-3 transition-colors"
          >
            {isPending ? "subiendo…" : "subir fuente"}
          </button>
          {result && !result.ok && (
            <p className="text-accent font-mono text-xs tracking-[1px]">
              ✗ {result.error}
            </p>
          )}
        </div>
      </form>

      {result && result.ok && (
        <div className="border border-divider bg-paper/30 p-6 space-y-4">
          <p className="font-mono text-[10px] tracking-[2.5px] uppercase text-accent">
            ✓ fuente creada · id #{result.source_id}
          </p>
          {result.referenced_song_slugs.length > 0 ? (
            <>
              <p className="font-serif text-lg text-ink">
                Detectadas <span className="text-accent">{result.referenced_song_slugs.length}</span> canción(es) mencionada(s):
              </p>
              <ul className="font-mono text-xs text-ink-dim space-y-1">
                {result.referenced_song_slugs.map((slug) => (
                  <li key={slug}>· {slug}</li>
                ))}
              </ul>
              <button
                type="button"
                onClick={handleProcess}
                disabled={isProcessing || processResult.status === "running"}
                data-cursor="hover"
                className="mt-2 border border-accent bg-accent text-white hover:bg-accent-soft disabled:opacity-50 disabled:cursor-wait font-mono text-[11px] tracking-[3px] uppercase px-7 py-3 transition-colors"
              >
                {processResult.status === "running"
                  ? "procesando… (puede tardar varios minutos)"
                  : "re-destilar y vectorizar"}
              </button>
            </>
          ) : (
            <p className="font-serif italic text-ink-dim">
              No se ha detectado ninguna canción del catálogo en el texto. La fuente queda guardada pero no dispara re-destilado.
            </p>
          )}

          {processResult.status === "done" && (
            <div className="border border-accent/30 bg-accent/5 p-4 mt-4">
              <p className="font-mono text-[10px] tracking-[2px] uppercase text-accent">
                ✓ {processResult.message}
              </p>
              {processResult.log && processResult.log.length > 0 && (
                <details className="mt-2">
                  <summary className="font-mono text-[10px] tracking-[2px] uppercase text-ink-dim cursor-pointer">
                    log
                  </summary>
                  <pre className="mt-2 text-[10px] text-ink-faint font-mono whitespace-pre-wrap max-h-64 overflow-auto">
                    {processResult.log.join("\n")}
                  </pre>
                </details>
              )}
            </div>
          )}
          {processResult.status === "error" && (
            <p className="text-accent font-mono text-xs tracking-[1px]">
              ✗ {processResult.message}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function Field({
  label, name, placeholder, hint, required,
}: { label: string; name: string; placeholder?: string; hint?: string; required?: boolean }) {
  return (
    <div>
      <label className="block font-mono text-[10px] tracking-[2px] uppercase text-ink-dim mb-1.5" htmlFor={name}>
        {label}
      </label>
      <input
        id={name}
        name={name}
        type="text"
        placeholder={placeholder}
        required={required}
        className="w-full bg-transparent border-0 border-b border-divider focus:border-accent focus:outline-none px-0 py-2 font-serif text-base text-ink"
      />
      {hint && <p className="text-ink-faint text-[10px] mt-1 font-mono tracking-[1px]">{hint}</p>}
    </div>
  );
}

function SelectField({
  label, name, options, defaultValue,
}: { label: string; name: string; options: { value: string; label: string }[]; defaultValue: string }) {
  return (
    <div>
      <label className="block font-mono text-[10px] tracking-[2px] uppercase text-ink-dim mb-1.5" htmlFor={name}>
        {label}
      </label>
      <select
        id={name}
        name={name}
        defaultValue={defaultValue}
        className="w-full bg-bg border border-divider focus:border-accent focus:outline-none px-3 py-2 font-mono text-xs text-ink"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </div>
  );
}

function TextareaField({
  label, name, placeholder, rows = 6,
}: { label: string; name: string; placeholder?: string; rows?: number }) {
  return (
    <div>
      <label className="block font-mono text-[10px] tracking-[2px] uppercase text-ink-dim mb-1.5" htmlFor={name}>
        {label}
      </label>
      <textarea
        id={name}
        name={name}
        rows={rows}
        placeholder={placeholder}
        className="w-full bg-bg border border-divider focus:border-accent focus:outline-none px-3 py-2 font-serif text-base text-ink resize-y"
      />
    </div>
  );
}
