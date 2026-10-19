"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { AdminPostDetail } from "./page";
import {
  ActionBar,
  Button,
  Field,
  Notice,
  StatusBadge,
  buttonClass,
  cx,
  filterClass,
  inputClass,
} from "@/components/admin/ui";
import { POST_STATUS, etiqueta } from "@/lib/admin/labels";


function todayISO(): string {
  // Fecha local en formato YYYY-MM-DD para el min del input y el valor por defecto.
  const now = new Date();
  const off = now.getTimezoneOffset();
  return new Date(now.getTime() - off * 60000).toISOString().slice(0, 10);
}

export default function PostEditor({ post }: { post: AdminPostDetail }) {
  const router = useRouter();
  const [tab, setTab] = useState<"edit" | "read">("read");
  const [title, setTitle] = useState(post.title);
  const [excerpt, setExcerpt] = useState(post.excerpt ?? "");
  const [metaTitle, setMetaTitle] = useState(post.meta_title ?? "");
  const [metaDescription, setMetaDescription] = useState(post.meta_description ?? "");
  const [bodyMd, setBodyMd] = useState(post.body_md);
  const [scheduleDate, setScheduleDate] = useState(todayISO());
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [status, setStatus] = useState(post.status);

  async function save() {
    setBusy("save");
    setMsg(null);
    try {
      const res = await fetch(`/biblioteca/admin/posts/api/update/${post.id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title,
          excerpt,
          body_md: bodyMd,
          meta_title: metaTitle,
          meta_description: metaDescription,
        }),
      });
      if (!res.ok) {
        setMsg(`Error ${res.status}: ${await res.text()}`);
        return;
      }
      setMsg("Cambios guardados ✓");
    } catch (e) {
      setMsg(`Error de red: ${e}`);
    } finally {
      setBusy(null);
    }
  }

  async function action(act: string, body?: unknown, redirectAfter = false) {
    setBusy(act);
    setMsg(null);
    try {
      const res = await fetch(`/biblioteca/admin/posts/api/${act}/${post.id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: body !== undefined ? JSON.stringify(body) : undefined,
      });
      if (!res.ok) {
        setMsg(`Error ${res.status}: ${await res.text()}`);
        return;
      }
      const data = (await res.json()) as { status?: string };
      if (redirectAfter) {
        router.push("/biblioteca/admin/blog");
        return;
      }
      if (data.status) setStatus(data.status);
      setMsg("Hecho ✓");
      router.refresh();
    } catch (e) {
      setMsg(`Error de red: ${e}`);
    } finally {
      setBusy(null);
    }
  }

  const st = etiqueta(POST_STATUS, status);
  const msgEsError = !!msg && msg.startsWith("Error");

  return (
    <div>
      <div className="flex items-center justify-between gap-3 mb-6 flex-wrap">
        <StatusBadge tone={st.tone} title={st.hint}>
          {st.label}
        </StatusBadge>
        <div className="flex gap-2" role="group" aria-label="Modo">
          <button
            type="button"
            aria-pressed={tab === "read"}
            onClick={() => setTab("read")}
            className={filterClass(tab === "read")}
          >
            Leer
          </button>
          <button
            type="button"
            aria-pressed={tab === "edit"}
            onClick={() => setTab("edit")}
            className={filterClass(tab === "edit")}
          >
            ✎ Editar
          </button>
        </div>
      </div>

      {tab === "read" ? (
        <article className="prose-ei">
          <h1 className="font-serif text-3xl md:text-4xl text-ink leading-tight mb-2">{title}</h1>
          {excerpt && <p className="font-serif italic text-ink-dim text-lg mb-6">{excerpt}</p>}
          <div className="font-serif text-ink/90 leading-relaxed [&_h2]:font-serif [&_h2]:text-2xl [&_h2]:text-ink [&_h2]:mt-8 [&_h2]:mb-3 [&_p]:mb-4 [&_a]:text-accent [&_a]:underline [&_strong]:text-ink [&_em]:italic">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{bodyMd}</ReactMarkdown>
          </div>
        </article>
      ) : (
        <div className="space-y-5">
          <Field label="Título" htmlFor="pe-title">
            <input
              id="pe-title"
              className={cx(inputClass, "font-serif text-lg")}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </Field>
          <Field label="Extracto" htmlFor="pe-excerpt" hint="El resumen que sale en listados y en la newsletter.">
            <textarea
              id="pe-excerpt"
              className={cx(inputClass, "min-h-[70px] font-serif")}
              value={excerpt}
              onChange={(e) => setExcerpt(e.target.value)}
            />
          </Field>
          <Field label="Cuerpo (Markdown)" htmlFor="pe-body">
            <textarea
              id="pe-body"
              className={cx(inputClass, "min-h-[460px] font-mono leading-relaxed")}
              value={bodyMd}
              onChange={(e) => setBodyMd(e.target.value)}
            />
          </Field>
          <div className="grid md:grid-cols-2 gap-4">
            <Field label="Título en Google (meta title)" htmlFor="pe-mt" hint={`${metaTitle.length} caracteres`}>
              <input id="pe-mt" className={inputClass} value={metaTitle} onChange={(e) => setMetaTitle(e.target.value)} />
            </Field>
            <Field
              label="Descripción en Google (meta description)"
              htmlFor="pe-md"
              hint={`${metaDescription.length} caracteres`}
            >
              <input
                id="pe-md"
                className={inputClass}
                value={metaDescription}
                onChange={(e) => setMetaDescription(e.target.value)}
              />
            </Field>
          </div>
          <Button
            variant="primary"
            onClick={save}
            disabled={busy !== null}
            loading={busy === "save"}
            loadingLabel="Guardando…"
          >
            Guardar cambios
          </Button>
        </div>
      )}

      {/* Barra de acciones de publicación */}
      <div className="mt-10 rounded-md border border-divider bg-paper p-4">
        <p className="font-medium text-ink">Publicación</p>
        {status === "scheduled" && (
          <p className="mt-1 text-sm text-ink-dim">
            Sale sola el{" "}
            <b className="text-ink">
              {post.scheduled_for
                ? new Date(post.scheduled_for).toLocaleDateString("es-ES", {
                    day: "numeric",
                    month: "long",
                    year: "numeric",
                    timeZone: "Europe/Madrid",
                  })
                : "—"}
            </b>
            .
          </p>
        )}
        {msg && (
          <div className="mt-3">
            <Notice tone={msgEsError ? "danger" : "ok"} onClose={() => setMsg(null)}>
              {msg}
            </Notice>
          </div>
        )}
        <ActionBar
          className="mt-3"
          primary={
            <>
              {status !== "published" && (
                <Button
                  variant="primary"
                  onClick={() => action("publish", undefined, true)}
                  disabled={busy !== null}
                  loading={busy === "publish"}
                >
                  Publicar ya
                </Button>
              )}
              {status !== "scheduled" && status !== "published" && (
                <span className="flex items-center gap-2">
                  <label htmlFor="pe-fecha" className="text-sm text-ink-dim">
                    o programar para
                  </label>
                  <input
                    id="pe-fecha"
                    type="date"
                    min={todayISO()}
                    value={scheduleDate}
                    onChange={(e) => setScheduleDate(e.target.value)}
                    className={cx(inputClass, "w-auto font-mono")}
                  />
                  <Button
                    onClick={() => action("schedule", { scheduled_for: scheduleDate })}
                    disabled={busy !== null || !scheduleDate}
                    loading={busy === "schedule"}
                  >
                    Programar
                  </Button>
                </span>
              )}
              {status === "scheduled" && (
                <Button onClick={() => action("unschedule")} disabled={busy !== null}>
                  Desprogramar
                </Button>
              )}
              {status === "published" && (
                <Link href={`/blog/${post.slug}`} target="_blank" className={buttonClass("secondary")}>
                  Ver en el blog ↗
                </Link>
              )}
            </>
          }
          danger={
            <>
              {status === "published" && (
                <Button variant="danger" onClick={() => action("unpublish")} disabled={busy !== null}>
                  Despublicar
                </Button>
              )}
              {status !== "rejected" && status !== "published" && (
                <Button
                  variant="danger"
                  onClick={() => {
                    if (window.confirm("¿Rechazar esta entrada?")) action("reject", undefined, true);
                  }}
                  disabled={busy !== null}
                >
                  Rechazar
                </Button>
              )}
            </>
          }
        />
      </div>
    </div>
  );
}
