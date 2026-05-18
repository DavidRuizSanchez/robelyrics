"use client";

import { useState, useTransition } from "react";
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

  return (
    <>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 mt-8">
        <div className="space-y-5">
          <SeoField
            label="h1"
            value={h1}
            onChange={setH1}
            placeholder={initial.resolved_h1}
            charsHint={`${h1.length} chars`}
          />
          <SeoField
            label="meta_title"
            value={metaTitle}
            onChange={setMetaTitle}
            placeholder={initial.resolved_title}
            charsHint={`${titleLen}/60`}
            warn={titleLen > 60}
          />
          <SeoField
            label="meta_description"
            value={metaDesc}
            onChange={setMetaDesc}
            placeholder={initial.resolved_description}
            charsHint={`${descLen}/160`}
            warn={descLen > 160}
            multiline
            rows={3}
          />
          <div>
            <label className="block font-mono text-[10px] tracking-[2px] uppercase text-ink-dim mb-1.5">
              body_md ({body.length} chars)
            </label>
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={28}
              className="w-full bg-bg border border-divider focus:border-accent focus:outline-none px-3 py-2 font-mono text-[13px] text-ink leading-[1.55] resize-y"
            />
          </div>
        </div>

        <div>
          <p className="font-mono text-[10px] tracking-[2px] uppercase text-ink-faint mb-3">
            preview
          </p>
          <div className="border border-divider p-5 max-h-[80vh] overflow-y-auto">
            <MarkdownArticle markdown={body} />
          </div>
        </div>
      </div>

      <div className="sticky bottom-0 mt-10 -mx-5 md:-mx-14 px-5 md:px-14 py-4 bg-bg/95 backdrop-blur border-t border-divider flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={onSave}
          disabled={isPending}
          data-cursor="hover"
          className="border border-divider hover:border-accent text-ink-dim hover:text-accent disabled:opacity-50 font-mono text-[11px] tracking-[3px] uppercase px-5 py-3 transition-colors"
        >
          {isPending ? "guardando…" : "guardar"}
        </button>
        {!published ? (
          <button
            type="button"
            onClick={onPublish}
            disabled={isPending}
            data-cursor="hover"
            className="border border-accent bg-accent text-white hover:bg-accent-bright disabled:opacity-50 font-mono text-[11px] tracking-[3px] uppercase px-5 py-3 transition-colors"
          >
            guardar y publicar
          </button>
        ) : (
          <button
            type="button"
            onClick={onUnpublish}
            disabled={isPending}
            data-cursor="hover"
            className="border border-accent text-accent hover:bg-accent hover:text-white disabled:opacity-50 font-mono text-[11px] tracking-[3px] uppercase px-5 py-3 transition-colors"
          >
            despublicar
          </button>
        )}

        <span className="font-mono text-[10px] tracking-[1.5px] uppercase ml-auto">
          estado:{" "}
          {published ? (
            <span className="text-accent">publicado</span>
          ) : reviewed ? (
            <span className="text-accent/70">revisado · sin publicar</span>
          ) : (
            <span className="text-ink-faint">sin revisar</span>
          )}
        </span>

        {feedback && (
          <span
            className={`font-mono text-[10px] tracking-[1.5px] uppercase ${
              feedback.ok ? "text-accent" : "text-red-400"
            }`}
          >
            {feedback.ok ? "✓ guardado" : `✗ ${feedback.error}`}
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
  return (
    <div>
      <div className="flex items-baseline justify-between mb-1.5 gap-3 flex-wrap">
        <label
          className={`font-mono text-[10px] tracking-[2px] uppercase ${
            warn ? "text-accent" : "text-ink-dim"
          }`}
        >
          {label} {charsHint ? `(${charsHint})` : ""}
        </label>
        <div className="flex items-center gap-3">
          {isOverride ? (
            <>
              <span className="font-mono text-[9px] tracking-[2px] uppercase text-accent">
                · override personalizado
              </span>
              <button
                type="button"
                onClick={() => onChange("")}
                data-cursor="hover"
                className="font-mono text-[9px] tracking-[2px] uppercase text-ink-faint hover:text-accent"
                title="Vaciar para usar la plantilla"
              >
                ↺ restaurar plantilla
              </button>
            </>
          ) : (
            <span className="font-mono text-[9px] tracking-[2px] uppercase text-ink-faint">
              · usando plantilla
            </span>
          )}
        </div>
      </div>
      {multiline ? (
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          rows={rows}
          placeholder={placeholder}
          className="w-full bg-bg border border-divider focus:border-accent focus:outline-none px-3 py-2 font-serif text-[15px] text-ink resize-y placeholder:italic placeholder:text-ink-faint/70"
        />
      ) : (
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="w-full bg-bg border border-divider focus:border-accent focus:outline-none px-3 py-2 font-serif text-[15px] text-ink placeholder:italic placeholder:text-ink-faint/70"
        />
      )}
    </div>
  );
}
