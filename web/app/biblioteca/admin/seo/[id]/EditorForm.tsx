"use client";

import { useState, useTransition } from "react";
import { Button, Field, StatusBadge, cx, inputClass } from "@/components/admin/ui";
import MarkdownArticle from "@/components/MarkdownArticle";
import {
  publishSeoAction,
  unpublishSeoAction,
  updateSeoAction,
  type SeoActionResult,
} from "./actions";

type SeoOut = {
  id: number;
  entity_type: string;
  slug: string;
  entity_label: string;
  body_md: string;
  meta_title: string | null;
  meta_description: string | null;
  h1: string | null;
  reviewed_at: string | null;
  published: boolean;
  public_url: string;
  resolved_title: string;
  resolved_description: string;
  resolved_h1: string;
};

export default function EditorForm({ initial }: { initial: SeoOut }) {
  const [body, setBody] = useState(initial.body_md);
  const [h1, setH1] = useState(initial.h1 || "");
  const [metaTitle, setMetaTitle] = useState(initial.meta_title || "");
  const [metaDesc, setMetaDesc] = useState(initial.meta_description || "");
  const [feedback, setFeedback] = useState<SeoActionResult | null>(null);
  const [published, setPublished] = useState(initial.published);
  const [reviewed, setReviewed] = useState(initial.reviewed_at !== null);
  const [isPending, startTransition] = useTransition();

  function buildFormData() {
    const fd = new FormData();
    fd.set("body_md", body);
    fd.set("h1", h1);
    fd.set("meta_title", metaTitle);
    fd.set("meta_description", metaDesc);
    return fd;
  }

  function onSave() {
    const fd = buildFormData();
    startTransition(async () => {
      const r = await updateSeoAction(initial.id, fd);
      setFeedback(r);
      if (r.ok) {
        setReviewed(true);
        setPublished(r.published);
      }
    });
  }

  function onPublish() {
    const fd = buildFormData();
    startTransition(async () => {
      const saved = await updateSeoAction(initial.id, fd);
      if (!saved.ok) {
        setFeedback(saved);
        return;
      }
      const r = await publishSeoAction(initial.id);
      setFeedback(r);
      if (r.ok) {
        setReviewed(true);
        setPublished(true);
      }
    });
  }

  function onUnpublish() {
    startTransition(async () => {
      const r = await unpublishSeoAction(initial.id);
      setFeedback(r);
      if (r.ok) setPublished(false);
    });
  }

  const titleLen = metaTitle.length;
  const descLen = metaDesc.length;

  const estado = published
    ? { label: "Publicada", tone: "ok" as const }
    : reviewed
      ? { label: "Revisada, sin publicar", tone: "warn" as const }
      : { label: "Sin revisar", tone: "neutral" as const };

  return (
    <>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 mt-8">
        <div className="space-y-5">
          <p className="text-sm text-ink-dim">
            Los campos vacíos usan la plantilla automática (se ve en gris dentro del campo). Escribe
            solo si quieres cambiarla.
          </p>
          <SeoField
            label="Título de la página (H1)"
            value={h1}
            onChange={setH1}
            placeholder={initial.resolved_h1}
            charsHint={`${h1.length} caracteres`}
          />
          <SeoField
            label="Título en Google (meta title)"
            value={metaTitle}
            onChange={setMetaTitle}
            placeholder={initial.resolved_title}
            charsHint={`${titleLen} de 60 caracteres`}
            warn={titleLen > 60}
          />
          <SeoField
            label="Descripción en Google (meta description)"
            value={metaDesc}
            onChange={setMetaDesc}
            placeholder={initial.resolved_description}
            charsHint={`${descLen} de 160 caracteres`}
            warn={descLen > 160}
            multiline
            rows={3}
          />
          <Field
            label={`Texto de la ficha (Markdown) · ${body.length.toLocaleString("es-ES")} caracteres`}
            htmlFor="seo-body"
          >
            <textarea
              id="seo-body"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={28}
              className={cx(inputClass, "font-mono leading-[1.55] resize-y")}
            />
          </Field>
        </div>

        <div>
          <p className="text-sm font-medium text-ink-dim mb-2">Vista previa</p>
          <div className="rounded-md border border-divider p-5 max-h-[80vh] overflow-y-auto">
            <MarkdownArticle markdown={body} />
          </div>
        </div>
      </div>

      {/* Barra fija: z-30 para quedar por debajo del aviso de erratas y del reproductor flotante. */}
      <div className="sticky bottom-0 z-30 mt-10 -mx-5 md:-mx-14 px-5 md:px-14 py-3 bg-bg/95 backdrop-blur border-t border-divider flex flex-wrap items-center gap-3">
        <Button onClick={onSave} disabled={isPending} loading={isPending} loadingLabel="Guardando…">
          Guardar
        </Button>
        {!published ? (
          <Button variant="primary" onClick={onPublish} disabled={isPending}>
            Guardar y publicar
          </Button>
        ) : (
          <Button variant="danger" onClick={onUnpublish} disabled={isPending}>
            Despublicar
          </Button>
        )}

        <StatusBadge tone={estado.tone} className="ml-auto">
          {estado.label}
        </StatusBadge>

        {feedback && (
          <span className={cx("text-sm", feedback.ok ? "text-ok" : "text-danger")} role="status">
            {feedback.ok ? "✓ Guardado" : `✗ ${feedback.error}`}
          </span>
        )}
      </div>
    </>
  );
}

function SeoField({
  label,
  value,
  onChange,
  placeholder,
  charsHint,
  warn,
  multiline,
  rows = 1,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
  charsHint?: string;
  warn?: boolean;
  multiline?: boolean;
  rows?: number;
}) {
  const isOverride = value.trim().length > 0;
  const id = "seo-" + label.replace(/\W+/g, "-").toLowerCase();
  return (
    <div>
      <div className="flex items-baseline justify-between mb-1 gap-3 flex-wrap">
        <label htmlFor={id} className="text-sm font-medium text-ink-dim">
          {label}
        </label>
        <div className="flex items-center gap-3 text-xs">
          {charsHint && <span className={warn ? "text-warn" : "text-ink-faint"}>{charsHint}{warn ? " · demasiado largo" : ""}</span>}
          {isOverride ? (
            <>
              <StatusBadge tone="info">Texto propio</StatusBadge>
              <button
                type="button"
                onClick={() => onChange("")}
                className="text-ink-faint hover:text-accent"
                title="Vaciar para usar la plantilla"
              >
                ↺ Volver a la plantilla
              </button>
            </>
          ) : (
            <StatusBadge>Plantilla automática</StatusBadge>
          )}
        </div>
      </div>
      {multiline ? (
        <textarea
          id={id}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          rows={rows}
          placeholder={placeholder}
          className={cx(inputClass, "font-serif text-[15px] resize-y placeholder:italic")}
        />
      ) : (
        <input
          id={id}
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className={cx(inputClass, "font-serif text-[15px] placeholder:italic")}
        />
      )}
    </div>
  );
}
