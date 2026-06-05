"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { AdminPostDetail } from "./page";

const STATUS_LABEL: Record<string, string> = {
  draft: "borrador",
  pending_review: "pendiente de revisar",
  approved: "aprobado",
  scheduled: "programado",
  published: "publicado",
  rejected: "rechazado",
};

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
        router.push("/biblioteca/admin/posts");
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

  const inputCls =
    "w-full bg-transparent border border-divider focus:border-accent outline-none text-ink px-3 py-2 font-serif";
  const labelCls =
    "font-mono text-[10px] tracking-[2px] uppercase text-ink-faint mb-1 block";
  const btnCls =
    "font-mono text-[10px] tracking-[2px] uppercase border px-3 py-1.5 disabled:opacity-40";

  return (
    <div>
      <div className="flex items-center justify-between gap-3 mb-6 flex-wrap">
        <span className="font-mono text-[10px] tracking-[2px] uppercase text-accent">
          estado: {STATUS_LABEL[status] ?? status}
        </span>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setTab("read")}
            data-cursor="hover"
            className={`${btnCls} ${tab === "read" ? "border-accent text-accent" : "border-divider text-ink-dim"}`}
          >
            leer
          </button>
          <button
            type="button"
            onClick={() => setTab("edit")}
            data-cursor="hover"
            className={`${btnCls} ${tab === "edit" ? "border-accent text-accent" : "border-divider text-ink-dim"}`}
          >
            editar
          </button>
        </div>
      </div>

      {tab === "read" ? (
        <article className="prose-ei">
          <h1 className="font-serif text-3xl md:text-4xl text-ink leading-tight mb-2">
            {title}
          </h1>
          {excerpt && (
            <p className="font-serif italic text-ink-dim text-lg mb-6">{excerpt}</p>
          )}
          <div className="font-serif text-ink/90 leading-relaxed [&_h2]:font-serif [&_h2]:text-2xl [&_h2]:text-ink [&_h2]:mt-8 [&_h2]:mb-3 [&_p]:mb-4 [&_a]:text-accent [&_a]:underline [&_strong]:text-ink [&_em]:italic">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{bodyMd}</ReactMarkdown>
          </div>
        </article>
      ) : (
        <div className="space-y-5">
          <div>
            <label className={labelCls}>título</label>
            <input className={inputCls} value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div>
            <label className={labelCls}>extracto</label>
            <textarea
              className={`${inputCls} min-h-[70px]`}
              value={excerpt}
              onChange={(e) => setExcerpt(e.target.value)}
            />
          </div>
          <div>
            <label className={labelCls}>cuerpo (markdown)</label>
            <textarea
              className={`${inputCls} min-h-[460px] font-mono text-sm leading-relaxed`}
              value={bodyMd}
              onChange={(e) => setBodyMd(e.target.value)}
            />
          </div>
          <div className="grid md:grid-cols-2 gap-4">
            <div>
              <label className={labelCls}>meta title (SEO)</label>
              <input className={inputCls} value={metaTitle} onChange={(e) => setMetaTitle(e.target.value)} />
            </div>
            <div>
              <label className={labelCls}>meta description (SEO)</label>
              <input
                className={inputCls}
                value={metaDescription}
                onChange={(e) => setMetaDescription(e.target.value)}
              />
            </div>
          </div>
          <button
            type="button"
            onClick={save}
            disabled={busy !== null}
            data-cursor="hover"
            className={`${btnCls} border-accent text-accent hover:bg-accent hover:text-white`}
          >
            {busy === "save" ? "guardando…" : "guardar cambios"}
          </button>
        </div>
      )}

      {/* Barra de acciones de publicación */}
      <div className="mt-10 pt-6 border-t border-divider">
        <p className="font-mono text-[10px] tracking-[2px] uppercase text-ink-faint mb-3">
          publicación
        </p>
        <div className="flex items-end gap-3 flex-wrap">
          {status !== "published" && (
            <button
              type="button"
              onClick={() => action("publish", undefined, true)}
              disabled={busy !== null}
              data-cursor="hover"
              className={`${btnCls} border-accent text-accent hover:bg-accent hover:text-white`}
            >
              publicar ya
            </button>
          )}

          {status !== "scheduled" && status !== "published" && (
            <div className="flex items-end gap-2">
              <div>
                <label className={labelCls}>programar para</label>
                <input
                  type="date"
                  min={todayISO()}
                  value={scheduleDate}
                  onChange={(e) => setScheduleDate(e.target.value)}
                  className="bg-transparent border border-divider focus:border-accent outline-none text-ink px-3 py-1.5 font-mono text-xs"
                />
              </div>
              <button
                type="button"
                onClick={() => action("schedule", { scheduled_for: scheduleDate })}
                disabled={busy !== null || !scheduleDate}
                data-cursor="hover"
                className={`${btnCls} border-divider text-ink-dim hover:border-accent hover:text-accent`}
              >
                programar
              </button>
            </div>
          )}

          {status === "scheduled" && (
            <>
              <span className="font-mono text-[11px] text-ink-dim">
                programado para{" "}
                {post.scheduled_for
                  ? new Date(post.scheduled_for).toLocaleDateString("es-ES", {
                      day: "numeric",
                      month: "long",
                      year: "numeric",
                    })
                  : "—"}
              </span>
              <button
                type="button"
                onClick={() => action("unschedule")}
                disabled={busy !== null}
                data-cursor="hover"
                className={`${btnCls} border-divider text-ink-dim hover:border-accent hover:text-accent`}
              >
                desprogramar
              </button>
            </>
          )}

          {status === "published" && (
            <>
              <Link
                href={`/blog/${post.slug}`}
                target="_blank"
                data-cursor="hover"
                className={`${btnCls} border-divider text-ink-dim hover:border-accent hover:text-accent`}
              >
                ver en el blog ↗
              </Link>
              <button
                type="button"
                onClick={() => action("unpublish")}
                disabled={busy !== null}
                data-cursor="hover"
                className={`${btnCls} border-divider text-ink-dim hover:border-accent hover:text-accent`}
              >
                despublicar
              </button>
            </>
          )}

          {status !== "rejected" && status !== "published" && (
            <button
              type="button"
              onClick={() => {
                if (window.confirm("¿Rechazar esta entrada?")) action("reject", undefined, true);
              }}
              disabled={busy !== null}
              data-cursor="hover"
              className={`${btnCls} border-divider text-ink-faint hover:text-ink`}
            >
              rechazar
            </button>
          )}
        </div>
        {msg && (
          <p className="mt-4 font-mono text-[11px] tracking-[1px] text-accent">{msg}</p>
        )}
      </div>
    </div>
  );
}
