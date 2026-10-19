"use client";

import { useState, useTransition } from "react";
import { Button, Callout, JobStatus, Notice, cx, filterClass, inputClass } from "@/components/admin/ui";
import { createSourceAction, processSourceAction, type SourceCreateResult } from "./actions";

type Tab = "text" | "url" | "youtube";

const KIND_OPTIONS = [
  { value: "manual", label: "Manual / pegado" },
  { value: "blog", label: "Blog" },
  { value: "forum", label: "Foro" },
  { value: "youtube_transcript", label: "Subtítulos de YouTube" },
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

  const TABS: { key: Tab; label: string; hint: string }[] = [
    { key: "text", label: "Pegar texto", hint: "Copias el análisis y lo pegas tal cual." },
    { key: "url", label: "Desde un enlace", hint: "Se descarga el texto de un blog o foro." },
    { key: "youtube", label: "Vídeo de YouTube", hint: "Se descargan los subtítulos del vídeo." },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap gap-2" role="tablist" aria-label="Cómo añadir la fuente">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={tab === t.key}
            onClick={() => setTab(t.key)}
            className={filterClass(tab === t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>
      <p className="-mt-3 text-sm text-ink-faint">{TABS.find((t) => t.key === tab)?.hint}</p>

      <form action={handleSubmit} className="space-y-5">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          <Field label="Enlace de la fuente *" name="url" placeholder="https://..." required hint="La dirección original, para citarla y no duplicarla." />
          <SelectField key={tab} label="Tipo de fuente" name="kind" options={KIND_OPTIONS} defaultValue={tab === "youtube" ? "youtube_transcript" : "manual"} />
          <Field label="Título" name="title" placeholder="Título del post, vídeo o fragmento" />
          <Field label="Autor" name="author" placeholder="Opcional" />
        </div>

        {tab === "text" && (
          <TextareaField
            label="Texto"
            name="content"
            placeholder="Pega aquí el análisis, comentario, hilo…"
            rows={10}
          />
        )}

        {tab === "url" && (
          <Field
            label="Enlace del que descargar el texto (si no es el de arriba)"
            name="fetch_url"
            placeholder="https://..."
            hint="Si lo dejas vacío, se descarga el enlace de la fuente."
          />
        )}

        {tab === "youtube" && (
          <Field
            label="Enlace del vídeo"
            name="youtube_url"
            placeholder="https://www.youtube.com/watch?v=..."
            hint="Se descargan los subtítulos en español si los tiene."
            required
          />
        )}

        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" variant="primary" loading={isPending} loadingLabel="Subiendo…">
            Añadir fuente
          </Button>
          {result && !result.ok && <Notice>{result.error}</Notice>}
        </div>
      </form>

      {result && result.ok && (
        <Callout tone="ok" title={`✓ Fuente guardada (#${result.source_id})`}>
          {result.referenced_song_slugs.length > 0 ? (
            <>
              <p>
                Habla de {result.referenced_song_slugs.length} canción
                {result.referenced_song_slugs.length === 1 ? "" : "es"} del catálogo:
              </p>
              <ul className="mt-1 flex flex-wrap gap-1.5">
                {result.referenced_song_slugs.map((slug) => (
                  <li key={slug} className="rounded border border-divider px-1.5 py-0.5 font-mono text-xs text-ink">
                    {slug}
                  </li>
                ))}
              </ul>
              <p className="mt-3">
                Para que se use, hay que volver a resumir y vectorizar esas canciones (tarda varios
                minutos y cuesta un poco de OpenAI).
              </p>
              <Button
                className="mt-2"
                variant="primary"
                onClick={handleProcess}
                disabled={isProcessing || processResult.status === "running"}
              >
                Incorporarla a esas canciones
              </Button>
            </>
          ) : (
            <p>
              No menciona ninguna canción del catálogo. Queda guardada, pero no cambia ninguna ficha.
            </p>
          )}

          {processResult.status === "running" && (
            <div className="mt-3">
              <JobStatus label="Incorporando" hint="puede tardar varios minutos" />
            </div>
          )}
          {processResult.status === "done" && (
            <div className="mt-3">
              <p className="font-medium text-ok">✓ {processResult.message}</p>
              {processResult.log && processResult.log.length > 0 && (
                <details className="mt-2">
                  <summary className="cursor-pointer text-sm text-ink-dim">Ver el registro técnico</summary>
                  <pre className="mt-2 text-xs text-ink-faint font-mono whitespace-pre-wrap max-h-64 overflow-auto">
                    {processResult.log.join("\n")}
                  </pre>
                </details>
              )}
            </div>
          )}
          {processResult.status === "error" && (
            <div className="mt-3">
              <Notice>{processResult.message}</Notice>
            </div>
          )}
        </Callout>
      )}
    </div>
  );
}

function Field({
  label, name, placeholder, hint, required,
}: { label: string; name: string; placeholder?: string; hint?: string; required?: boolean }) {
  return (
    <div className="space-y-1">
      <label className="block text-sm font-medium text-ink-dim" htmlFor={name}>
        {label}
      </label>
      <input id={name} name={name} type="text" placeholder={placeholder} required={required} className={inputClass} />
      {hint && <p className="text-xs text-ink-faint">{hint}</p>}
    </div>
  );
}

function SelectField({
  label, name, options, defaultValue,
}: { label: string; name: string; options: { value: string; label: string }[]; defaultValue: string }) {
  return (
    <div className="space-y-1">
      <label className="block text-sm font-medium text-ink-dim" htmlFor={name}>
        {label}
      </label>
      <select id={name} name={name} defaultValue={defaultValue} className={inputClass}>
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
    <div className="space-y-1">
      <label className="block text-sm font-medium text-ink-dim" htmlFor={name}>
        {label}
      </label>
      <textarea id={name} name={name} rows={rows} placeholder={placeholder} className={cx(inputClass, "font-serif text-base resize-y")} />
    </div>
  );
}
