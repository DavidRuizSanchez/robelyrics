"use client";

import { useState } from "react";
import type { IGAccount, IGItem, IGNewsCandidate } from "./page";

const STATUS_LABEL: Record<string, string> = {
  pending: "Pendiente",
  prepared: "Preparado",
  published: "Publicado",
  failed: "Fallido",
  discarded: "Descartado",
};

const STATUS_COLOR: Record<string, string> = {
  pending: "border-divider text-ink-dim",
  prepared: "border-accent text-accent",
  published: "border-accent bg-accent/10 text-accent",
  failed: "border-red-500/60 text-red-400",
  discarded: "border-divider text-ink-faint",
};

const STATUS_ORDER = ["pending", "prepared", "failed", "published", "discarded"];

function fmtDate(iso: string): string {
  if (!iso) return "";
  return new Date(iso + (iso.includes("T") ? "" : "T00:00:00")).toLocaleDateString(
    "es-ES",
    { weekday: "short", day: "numeric", month: "short" },
  );
}

export default function InstagramPlanner({
  queue,
  candidates,
  account,
}: {
  queue: IGItem[];
  candidates: IGNewsCandidate[];
  account: IGAccount;
}) {
  const [busy, setBusy] = useState<string | null>(null);

  async function call(method: "POST", url: string, body?: unknown) {
    setBusy(url);
    try {
      const res = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: body ? JSON.stringify(body) : undefined,
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        alert(data.error || `Error ${res.status}`);
        return;
      }
      window.location.reload();
    } catch (e) {
      alert(`Error de red: ${e}`);
    } finally {
      setBusy(null);
    }
  }

  function enqueueNews(id: number) {
    call("POST", "/biblioteca/admin/instagram/api/enqueue", { news_item_id: id });
  }

  function prepare(id: number) {
    call("POST", `/biblioteca/admin/instagram/api/queue/${id}/prepare`);
  }

  function publish(id: number, dryRun: boolean) {
    const msg = dryRun
      ? "¿Solo preparar este post (no publicar)?"
      : "¿Publicar este post en Instagram AHORA?";
    if (!window.confirm(msg)) return;
    call(
      "POST",
      `/biblioteca/admin/instagram/api/queue/${id}/publish`,
      { dry_run: dryRun },
    );
  }

  function discard(id: number) {
    if (!window.confirm("¿Descartar este post?")) return;
    call("POST", `/biblioteca/admin/instagram/api/queue/${id}/discard`);
  }

  // Agrupa la cola por estado, en el orden que nos importa al admin.
  const byStatus = new Map<string, IGItem[]>();
  for (const s of STATUS_ORDER) byStatus.set(s, []);
  for (const it of queue) {
    if (!byStatus.has(it.status)) byStatus.set(it.status, []);
    byStatus.get(it.status)!.push(it);
  }

  const candidateIdsInQueue = new Set(
    queue
      .map((q) => {
        const m = q.source_url ? candidates.find((c) => c.url === q.source_url) : null;
        return m?.id;
      })
      .filter((x): x is number => typeof x === "number"),
  );

  return (
    <div className="space-y-14">
      {/* ---------- Cola ---------- */}
      {STATUS_ORDER.map((s) => {
        const items = byStatus.get(s) ?? [];
        if (items.length === 0) return null;
        return (
          <section key={s}>
            <h2 className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-5">
              {STATUS_LABEL[s] ?? s} · {items.length}
            </h2>
            <ul className="divide-y divide-divider">
              {items.map((it) => (
                <li key={it.id} className="py-5">
                  <div className="flex items-start justify-between gap-4 flex-wrap">
                    <div className="flex-1 min-w-0">
                      <p className="font-mono text-[9px] tracking-[2px] uppercase text-ink-faint mb-1">
                        {fmtDate(it.day)} · slot {it.slot} ·{" "}
                        {it.is_blog ? "Blog" : it.category ?? "Actualidad"}
                        {it.source_name && ` · ${it.source_name}`}
                      </p>
                      <p className="font-serif text-lg text-ink leading-tight">
                        {it.title}
                      </p>
                      {it.summary && (
                        <p className="mt-1 font-serif italic text-ink-dim text-sm leading-relaxed line-clamp-2">
                          {it.summary}
                        </p>
                      )}
                      <div className="mt-2 flex items-center gap-3 flex-wrap">
                        <span
                          className={`font-mono text-[9px] tracking-[2px] uppercase border px-1.5 py-0.5 ${STATUS_COLOR[it.status] ?? ""}`}
                        >
                          {STATUS_LABEL[it.status] ?? it.status}
                        </span>
                        {it.is_prepared && (
                          <span className="font-mono text-[9px] tracking-[2px] uppercase text-ink-faint">
                            imagen ✓
                          </span>
                        )}
                        {it.has_caption && (
                          <span className="font-mono text-[9px] tracking-[2px] uppercase text-ink-faint">
                            caption ✓
                          </span>
                        )}
                        {it.ig_media_id && (
                          <a
                            href={`https://www.instagram.com/p/${it.ig_media_id}/`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="font-mono text-[10px] text-accent hover:underline"
                          >
                            ver en IG ↗
                          </a>
                        )}
                        {it.source_url && (
                          <a
                            href={it.source_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="font-mono text-[10px] text-ink-dim hover:text-accent"
                          >
                            fuente ↗
                          </a>
                        )}
                      </div>
                      {it.error && (
                        <p className="mt-2 font-mono text-[10px] text-red-400">
                          {it.error}
                        </p>
                      )}
                    </div>
                    <div className="shrink-0 flex items-center gap-2 flex-wrap">
                      {it.status !== "published" && it.status !== "discarded" && (
                        <>
                          <button
                            type="button"
                            disabled={busy !== null}
                            onClick={() => prepare(it.id)}
                            data-cursor="hover"
                            className="font-mono text-[10px] tracking-[2px] uppercase border border-divider hover:border-accent hover:text-accent text-ink-dim px-3 py-1.5 disabled:opacity-40"
                          >
                            {it.is_prepared ? "re-preparar" : "preparar"}
                          </button>
                          {it.is_prepared && (
                            <button
                              type="button"
                              disabled={busy !== null || !account.ok}
                              onClick={() => publish(it.id, false)}
                              data-cursor="hover"
                              title={
                                account.ok ? "" : "El token de IG no es válido"
                              }
                              className="font-mono text-[10px] tracking-[2px] uppercase border border-accent text-accent hover:bg-accent hover:text-white px-3 py-1.5 disabled:opacity-40"
                            >
                              ▶ publicar ahora
                            </button>
                          )}
                          <button
                            type="button"
                            disabled={busy !== null}
                            onClick={() => discard(it.id)}
                            data-cursor="hover"
                            className="font-mono text-[10px] tracking-[2px] uppercase border border-divider hover:border-divider-strong text-ink-faint hover:text-ink px-3 py-1.5 disabled:opacity-40"
                          >
                            descartar
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          </section>
        );
      })}

      {queue.length === 0 && (
        <p className="font-serif italic text-ink-dim">
          La cola está vacía. Encola alguna noticia desde el banco de abajo o
          espera al cron diario.
        </p>
      )}

      {/* ---------- Banco de noticias para encolar ---------- */}
      <section>
        <h2 className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-1">
          Noticias agregadas · {candidates.length}
        </h2>
        <p className="font-serif italic text-ink-dim text-sm mb-5">
          Top noticias del último ciclo del agregador. Las que ya están en
          cola no se pueden volver a encolar.
        </p>
        {candidates.length === 0 ? (
          <p className="font-serif italic text-ink-faint">
            No hay noticias en el almacén. Corre primero el agregador.
          </p>
        ) : (
          <ul className="divide-y divide-divider">
            {candidates.map((n) => {
              const ya = candidateIdsInQueue.has(n.id);
              return (
                <li key={n.id} className="py-4">
                  <div className="flex items-start justify-between gap-4 flex-wrap">
                    <div className="flex-1 min-w-0">
                      <p className="font-mono text-[9px] tracking-[2px] uppercase text-ink-faint mb-1">
                        {n.category ?? "Actualidad"} ·{" "}
                        {n.source_medium ?? n.source_name} · score{" "}
                        <span className="text-accent">
                          {n.relevance_score.toFixed(1)}
                        </span>
                        {n.policy === "ig-only" && (
                          <span className="ml-2 text-accent">[ig-only]</span>
                        )}
                      </p>
                      <p className="font-serif text-base text-ink leading-tight">
                        {n.title}
                      </p>
                      <a
                        href={n.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="font-mono text-[10px] text-ink-dim hover:text-accent"
                      >
                        ver original ↗
                      </a>
                    </div>
                    <button
                      type="button"
                      disabled={busy !== null || ya}
                      onClick={() => enqueueNews(n.id)}
                      data-cursor="hover"
                      className="font-mono text-[10px] tracking-[2px] uppercase border border-accent text-accent hover:bg-accent hover:text-white px-3 py-1.5 disabled:opacity-40"
                    >
                      {ya ? "ya en cola" : "📷 encolar"}
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}
