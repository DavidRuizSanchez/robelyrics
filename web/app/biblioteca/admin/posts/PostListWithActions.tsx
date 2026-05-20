"use client";

import Link from "next/link";
import { useState } from "react";

type AdminPostItem = {
  id: number;
  slug: string;
  kind: string;
  status: string;
  title: string;
  excerpt: string | null;
  source_url: string | null;
  source_name: string | null;
  created_at: string;
  published_at: string | null;
};

const KIND_LABEL: Record<string, string> = {
  editorial: "Editorial",
  news: "Noticia",
  anniversary: "Efeméride",
};

const STATUS_LABEL: Record<string, { label: string; cls: string }> = {
  draft: { label: "borrador", cls: "text-ink-faint" },
  pending_review: { label: "pendiente", cls: "text-accent" },
  approved: { label: "aprobado", cls: "text-ink" },
  published: { label: "publicado", cls: "text-accent" },
  rejected: { label: "rechazado", cls: "text-ink-faint" },
};

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("es-ES", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export default function PostListWithActions({ items }: { items: AdminPostItem[] }) {
  const [busy, setBusy] = useState<number | null>(null);

  async function act(id: number, action: "publish" | "reject" | "unpublish") {
    setBusy(id);
    try {
      const res = await fetch(`/biblioteca/admin/posts/api/${action}/${id}`, {
        method: "POST",
      });
      if (!res.ok) {
        const text = await res.text();
        alert(`Error ${res.status}: ${text}`);
        return;
      }
      window.location.reload();
    } catch (e) {
      alert(`Error de red: ${e}`);
    } finally {
      setBusy(null);
    }
  }

  if (items.length === 0) {
    return (
      <p className="font-serif italic text-ink-dim text-lg mt-6">
        No hay entradas que coincidan con el filtro.
      </p>
    );
  }

  return (
    <ul className="divide-y divide-divider">
      {items.map((p) => {
        const st = STATUS_LABEL[p.status] ?? { label: p.status, cls: "text-ink-faint" };
        const canPublish = p.status === "pending_review" || p.status === "approved" || p.status === "draft";
        const canReject = p.status === "pending_review" || p.status === "draft";
        const canUnpublish = p.status === "published";
        return (
          <li key={p.id} className="py-5">
            <div className="flex items-start justify-between gap-4 flex-wrap">
              <div className="flex-1 min-w-0">
                <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-1">
                  {KIND_LABEL[p.kind] || p.kind} · creado {formatDate(p.created_at)}
                  {p.published_at && ` · publicado ${formatDate(p.published_at)}`}
                </p>
                <h3 className="font-serif text-xl md:text-2xl text-ink leading-tight">
                  {p.title}
                </h3>
                {p.excerpt && (
                  <p className="mt-2 font-serif italic text-ink-dim text-base leading-relaxed max-w-[680px]">
                    {p.excerpt}
                  </p>
                )}
                {p.source_url && p.source_name && (
                  <p className="mt-2 font-mono text-[10px] tracking-[1px] text-ink-faint">
                    Fuente:{" "}
                    <a
                      href={p.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-accent hover:underline"
                    >
                      {p.source_name} ↗
                    </a>
                  </p>
                )}
              </div>
              <div className="shrink-0 flex flex-col items-end gap-2">
                <span className={`font-mono text-[10px] tracking-[2px] uppercase ${st.cls}`}>
                  {st.label}
                </span>
                <div className="flex gap-2 flex-wrap justify-end">
                  {p.status === "published" && (
                    <Link
                      href={`/blog/${p.slug}`}
                      target="_blank"
                      data-cursor="hover"
                      className="font-mono text-[10px] tracking-[2px] uppercase border border-divider hover:border-accent hover:text-accent text-ink-dim px-3 py-1.5"
                    >
                      ver ↗
                    </Link>
                  )}
                  {canPublish && (
                    <button
                      type="button"
                      onClick={() => act(p.id, "publish")}
                      disabled={busy === p.id}
                      data-cursor="hover"
                      className="font-mono text-[10px] tracking-[2px] uppercase border border-accent text-accent hover:bg-accent hover:text-white px-3 py-1.5 disabled:opacity-40"
                    >
                      publicar
                    </button>
                  )}
                  {canUnpublish && (
                    <button
                      type="button"
                      onClick={() => act(p.id, "unpublish")}
                      disabled={busy === p.id}
                      data-cursor="hover"
                      className="font-mono text-[10px] tracking-[2px] uppercase border border-divider hover:border-accent hover:text-accent text-ink-dim px-3 py-1.5 disabled:opacity-40"
                    >
                      despublicar
                    </button>
                  )}
                  {canReject && (
                    <button
                      type="button"
                      onClick={() => {
                        if (window.confirm("¿Rechazar esta entrada?")) act(p.id, "reject");
                      }}
                      disabled={busy === p.id}
                      data-cursor="hover"
                      className="font-mono text-[10px] tracking-[2px] uppercase border border-divider hover:border-divider-strong text-ink-faint hover:text-ink px-3 py-1.5 disabled:opacity-40"
                    >
                      rechazar
                    </button>
                  )}
                </div>
              </div>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
