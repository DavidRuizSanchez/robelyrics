"use client";

import { useState } from "react";
import type { IGAccount, IGItem, IGNewsCandidate } from "./page";
import InstagramPreview, { type PreviewMedia } from "./InstagramPreview";
import ProgramarPost from "./ProgramarPost";

const STATUS_LABEL: Record<string, string> = {
  proposed: "Propuesta",
  pending: "Pendiente",
  prepared: "Preparado",
  published: "Publicado",
  failed: "Fallido",
  discarded: "Descartado",
};

const STATUS_COLOR: Record<string, string> = {
  proposed: "border-accent/50 text-accent/80",
  pending: "border-divider text-ink-dim",
  prepared: "border-accent text-accent",
  published: "border-accent bg-accent/10 text-accent",
  failed: "border-red-500/60 text-red-400",
  discarded: "border-divider text-ink-faint",
};

// Etiqueta legible del tipo de contenido evergreen.
const CONTENT_TYPE_LABEL: Record<string, string> = {
  quote: "Frase de canción",
  ephemeris: "Efeméride",
  anecdote: "Anécdota",
  robe_quote: "Cita de Robe",
  news: "Noticia",
  blog: "Blog",
};

// Estados que NO entran en la cola de publicación arrastrable (solo lectura).
const TERMINAL_ORDER = ["failed", "published", "discarded"];
// Estados publicables: se muestran juntos en una sola cola ordenable.
const UPCOMING_STATUSES = new Set(["pending", "prepared"]);

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

  // Cola de GOTEO: pending + prepared SIN fecha fija, ordenados por `position`.
  // Estado local para el drag-and-drop optimista.
  const [upcoming, setUpcoming] = useState<IGItem[]>(() =>
    queue
      .filter((it) => UPCOMING_STATUSES.has(it.status) && !it.publish_on)
      .sort((a, b) => a.position - b.position || a.id - b.id),
  );
  // Con momento fijado: efemérides (día del aniversario) y posts programados a
  // mano con fecha y hora. Ninguno entra en el goteo.
  const pinned = queue
    .filter(
      (it) => UPCOMING_STATUSES.has(it.status) && (it.publish_on || it.publish_at),
    )
    .sort((a, b) =>
      (a.publish_on || a.publish_at || "").localeCompare(
        b.publish_on || b.publish_at || "",
      ),
    );
  // Programaciones cambiadas en esta sesión, para reflejarlas sin recargar.
  const [schedules, setSchedules] = useState<Record<number, string | null>>({});
  const scheduleOf = (it: IGItem) =>
    it.id in schedules ? schedules[it.id] : it.publish_at;
  const [dragIndex, setDragIndex] = useState<number | null>(null);

  // Ver/editar el contenido de un item (clic en el título lo despliega).
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<{
    caption: string | null;
    image_b64: string | null;
    image_url: string | null;
    media?: PreviewMedia[];
  } | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [draftCaption, setDraftCaption] = useState("");
  const [savedFlash, setSavedFlash] = useState(false);

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

  // --- Propuestas evergreen: selección múltiple + acciones en bloque ---
  const proposed = queue
    .filter((it) => it.status === "proposed")
    .sort((a, b) => a.content_type.localeCompare(b.content_type) || a.id - b.id);
  const [selected, setSelected] = useState<Set<number>>(new Set());

  function toggleSelected(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleSelectAll() {
    setSelected((prev) =>
      prev.size === proposed.length ? new Set() : new Set(proposed.map((it) => it.id)),
    );
  }

  function bulkApprove() {
    const ids = [...selected];
    if (ids.length === 0) return;
    if (
      !window.confirm(
        `¿Aprobar ${ids.length} propuesta(s)? Se les generará imagen + caption y entrarán en la cola de publicación.`,
      )
    )
      return;
    call("POST", "/biblioteca/admin/instagram/api/queue/bulk/approve", { ids });
  }

  function bulkDiscard() {
    const ids = [...selected];
    if (ids.length === 0) return;
    if (!window.confirm(`¿Descartar ${ids.length} propuesta(s)?`)) return;
    call("POST", "/biblioteca/admin/instagram/api/queue/bulk/discard", { ids });
  }

  function interleave() {
    if (!window.confirm("¿Reordenar la cola intercalando los tipos de publicación?")) return;
    call("POST", "/biblioteca/admin/instagram/api/queue/interleave");
  }

  // --- Preparar en bloque lo que se quedó sin material ---
  // Hace falta porque «variar formatos» limpia el material de todo lo que
  // cambia de tipo: las diapositivas de un carrusel no sirven para un reel.
  async function bulkPrepare() {
    const sinMaterial = upcoming.filter((it) => !it.is_prepared).length;
    if (sinMaterial === 0) {
      window.alert("Todo lo de la cola ya tiene su material generado.");
      return;
    }
    if (
      !window.confirm(
        `${sinMaterial} publicaci\u00f3n(es) sin material. ¿Generarlo ahora?\n\n` +
          "Los reels y carruseles tardan un rato y tienen coste. Se hacen hasta 20 por tanda.",
      )
    )
      return;
    await call("POST", "/biblioteca/admin/instagram/api/queue/bulk/prepare", {
      limit: 20,
    });
  }

  // --- Variar formatos: que el feed no salga todo del mismo tipo ---
  async function shuffleFormats() {
    // Semilla distinta en cada pulsación: volver a darle da otro reparto.
    const seed = Math.floor(Date.now() / 1000) % 9973;
    setBusy("shuffle");
    try {
      const res = await fetch(
        "/biblioteca/admin/instagram/api/queue/shuffle-formats",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ seed, only_scheduled: false }),
        },
      ).then((r) => r.json());
      if (res.error) throw new Error(res.error);

      const n = res.changed?.length ?? 0;
      if (n === 0) {
        window.alert(
          `Ya estaban repartidos según la mezcla (${res.mix?.join(" · ")}).`,
        );
        return;
      }
      const ETIQUETA: Record<string, string> = {
        IMAGE: "foto", CAROUSEL: "carrusel", REELS: "reel",
      };
      const muestra = res.changed
        .slice(0, 8)
        .map(
          (c: { title: string; antes: string; ahora: string }) =>
            `· ${ETIQUETA[c.antes] ?? c.antes} → ${ETIQUETA[c.ahora] ?? c.ahora}  ${c.title}`,
        )
        .join("\n");
      const cola = n > 8 ? `\n… y ${n - 8} más` : "";
      window.alert(
        `${n} publicaciones cambian de formato:\n\n${muestra}${cola}\n\n` +
          "Vuelven a «pendiente»: hay que re-prepararlas para regenerar el material.",
      );
      window.location.reload();
    } catch (e) {
      window.alert(e instanceof Error ? e.message : "no se pudo repartir");
    } finally {
      setBusy(null);
    }
  }

  // --- Autoprogramar: reparte lo aprobado por las próximas semanas ---
  async function autoSchedule() {
    setBusy("auto-schedule");
    try {
      // Primero en seco, para enseñar el reparto ANTES de escribir nada.
      const previa = await fetch(
        "/biblioteca/admin/instagram/api/queue/auto-schedule",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ weeks: 4, dry_run: true }),
        },
      ).then((r) => r.json());

      if (previa.error) throw new Error(previa.error);
      const n = previa.scheduled?.length ?? 0;
      if (n === 0) {
        window.alert(
          previa.skipped?.length
            ? `Nada que programar. ${previa.skipped.length} sin hueco (tope ${previa.weekly_cap}/semana).`
            : "No hay posts aprobados sin fecha que programar.",
        );
        return;
      }
      const muestra = previa.scheduled
        .slice(0, 6)
        .map(
          (s: { title: string; when: string }) =>
            `· ${new Date(s.when).toLocaleString("es-ES", {
              weekday: "short", day: "numeric", month: "short",
              hour: "2-digit", minute: "2-digit",
            })} — ${s.title}`,
        )
        .join("\n");
      const cola =
        previa.scheduled.length > 6
          ? `\n… y ${previa.scheduled.length - 6} más`
          : "";
      const fuera = previa.skipped?.length
        ? `\n\n${previa.skipped.length} se quedan fuera por falta de hueco.`
        : "";
      const ok = window.confirm(
        `Se van a programar ${n} posts (máx. ${previa.weekly_cap}/semana, ` +
          `en los slots ${previa.slots?.join(" y ")}):\n\n${muestra}${cola}${fuera}` +
          `\n\n¿Confirmas?`,
      );
      if (!ok) return;

      await call(
        "POST",
        "/biblioteca/admin/instagram/api/queue/auto-schedule",
        { weeks: 4 },
      );
    } catch (e) {
      window.alert(e instanceof Error ? e.message : "no se pudo autoprogramar");
    } finally {
      setBusy(null);
    }
  }

  // --- Drag-and-drop de la cola de publicación ---
  function onDragStart(index: number) {
    setDragIndex(index);
  }

  function onDragOver(index: number, e: React.DragEvent) {
    e.preventDefault();
    if (dragIndex === null || dragIndex === index) return;
    setUpcoming((prev) => {
      const next = [...prev];
      const [moved] = next.splice(dragIndex, 1);
      next.splice(index, 0, moved);
      return next;
    });
    setDragIndex(index);
  }

  async function persistOrder() {
    const ids = upcoming.map((it) => it.id);
    setDragIndex(null);
    setBusy("reorder");
    try {
      const res = await fetch("/biblioteca/admin/instagram/api/reorder", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        alert(data.error || `Error ${res.status}`);
        window.location.reload(); // re-sincroniza con el servidor
      }
    } catch (e) {
      alert(`Error de red: ${e}`);
      window.location.reload();
    } finally {
      setBusy(null);
    }
  }

  // Clic en el título: despliega el detalle (imagen + caption) y lo carga.
  async function toggleDetail(id: number) {
    if (expandedId === id) {
      setExpandedId(null);
      setDetail(null);
      return;
    }
    setExpandedId(id);
    setDetail(null);
    setSavedFlash(false);
    setDetailLoading(true);
    try {
      const res = await fetch(`/biblioteca/admin/instagram/api/queue/${id}`);
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        alert(d.error || `Error ${res.status}`);
        setExpandedId(null);
        return;
      }
      const data = await res.json();
      setDetail({
        caption: data.caption ?? null,
        image_b64: data.image_b64 ?? null,
        image_url: data.image_url ?? null,
      });
      setDraftCaption(data.caption ?? "");
    } catch (e) {
      alert(`Error de red: ${e}`);
      setExpandedId(null);
    } finally {
      setDetailLoading(false);
    }
  }

  async function saveCaption(id: number) {
    setBusy("save");
    try {
      const res = await fetch(`/biblioteca/admin/instagram/api/queue/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ caption: draftCaption }),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        alert(d.error || `Error ${res.status}`);
        return;
      }
      const data = await res.json();
      setDetail({
        caption: data.caption ?? null,
        image_b64: data.image_b64 ?? null,
        image_url: data.image_url ?? null,
      });
      setSavedFlash(true);
    } catch (e) {
      alert(`Error de red: ${e}`);
    } finally {
      setBusy(null);
    }
  }

  // Estados terminales agrupados (solo lectura), tal cual venían de la API.
  const byTerminal = new Map<string, IGItem[]>();
  for (const s of TERMINAL_ORDER) byTerminal.set(s, []);
  for (const it of queue) {
    if (byTerminal.has(it.status)) byTerminal.get(it.status)!.push(it);
  }

  const candidateIdsInQueue = new Set(
    queue
      .map((q) => {
        const m = q.source_url ? candidates.find((c) => c.url === q.source_url) : null;
        return m?.id;
      })
      .filter((x): x is number => typeof x === "number"),
  );

  function ItemMeta({ it }: { it: IGItem }) {
    return (
      <>
        <p className="font-mono text-[9px] tracking-[2px] uppercase text-ink-faint mb-1">
          {fmtDate(it.day)} · slot {it.slot} ·{" "}
          {it.is_blog ? "Blog" : it.category ?? "Actualidad"}
          {it.source_name && ` · ${it.source_name}`}
        </p>
        <button
          type="button"
          onClick={() => toggleDetail(it.id)}
          data-cursor="hover"
          className="text-left font-serif text-lg text-ink leading-tight hover:text-accent transition-colors"
          title="Ver / editar el contenido"
        >
          {it.title}
          <span className="ml-2 font-mono text-[10px] text-ink-faint">
            {expandedId === it.id ? "▲" : "▼"}
          </span>
        </button>
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
          {it.media_type && it.media_type !== "IMAGE" && (
            <span className="font-mono text-[9px] tracking-[2px] uppercase border border-divider text-ink-dim px-1.5 py-0.5">
              {it.media_type === "CAROUSEL"
                ? `▣ carrusel · ${it.media_count}`
                : "▶ reel"}
            </span>
          )}
          {scheduleOf(it) && (
            <span className="font-mono text-[9px] tracking-[2px] uppercase border border-accent/60 text-accent px-1.5 py-0.5">
              🕒{" "}
              {new Date(scheduleOf(it) as string).toLocaleString("es-ES", {
                day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
              })}
            </span>
          )}
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
          <p className="mt-2 font-mono text-[10px] text-red-400">{it.error}</p>
        )}

        {expandedId === it.id && (
          <div className="mt-4 border-l-2 border-accent/40 pl-4">
            {detailLoading ? (
              <p className="font-mono text-[10px] tracking-[2px] uppercase text-ink-faint">
                cargando…
              </p>
            ) : (
              <div className="flex flex-col md:flex-row gap-6">
                {/* Vista previa fiel al feed: imagen + caption con su corte
                    real. Es donde se ve si la primera línea dice algo. */}
                <InstagramPreview
                  imageSrc={
                    detail?.image_b64
                      ? `data:image/jpeg;base64,${detail.image_b64}`
                      : detail?.image_url ?? null
                  }
                  caption={
                    it.status === "published"
                      ? detail?.caption ?? ""
                      : draftCaption
                  }
                  media={detail?.media ?? []}
                  mediaSrc={(pos) =>
                    `/biblioteca/admin/instagram/api/queue/${it.id}/media/${pos}`
                  }
                  formatoPedido={it.media_type}
                />

                {/* Editor del caption */}
                <div className="flex-1 min-w-0">
                  <label className="font-mono text-[9px] tracking-[2px] uppercase text-ink-faint">
                    caption
                  </label>
                  {it.status === "published" ? (
                    <p className="mt-1 font-serif text-sm text-ink-dim whitespace-pre-wrap">
                      {detail?.caption || "(sin caption)"}
                    </p>
                  ) : (
                    <>
                      <textarea
                        value={draftCaption}
                        onChange={(e) => {
                          setDraftCaption(e.target.value);
                          setSavedFlash(false);
                        }}
                        rows={8}
                        className="mt-1 w-full bg-transparent border border-divider focus:border-accent outline-none text-ink text-sm font-serif leading-relaxed p-2 resize-y"
                      />
                      <div className="mt-2 flex items-center gap-3">
                        <button
                          type="button"
                          disabled={busy !== null || draftCaption === (detail?.caption ?? "")}
                          onClick={() => saveCaption(it.id)}
                          data-cursor="hover"
                          className="font-mono text-[10px] tracking-[2px] uppercase border border-accent text-accent hover:bg-accent hover:text-white px-3 py-1.5 disabled:opacity-40"
                        >
                          guardar caption
                        </button>
                        {savedFlash && (
                          <span className="font-mono text-[10px] tracking-[2px] uppercase text-accent">
                            guardado ✓
                          </span>
                        )}
                        <span className="font-mono text-[9px] text-ink-faint">
                          {draftCaption.length} car.
                        </span>
                      </div>
                      <p className="mt-2 font-mono text-[9px] text-ink-faint leading-relaxed">
                        Ojo: "re-preparar" regenera el caption y la imagen desde
                        cero (pierde esta edición). Edita justo antes de publicar.
                      </p>

                      <div className="mt-4 pt-4 border-t border-divider">
                        <label className="font-mono text-[9px] tracking-[2px] uppercase text-ink-faint">
                          formato
                        </label>
                        <div className="mt-1 flex items-center gap-2 flex-wrap">
                          <select
                            value={it.media_type || "IMAGE"}
                            disabled={busy !== null}
                            onChange={async (e) => {
                              const nuevo = e.target.value;
                              await fetch(
                                `/biblioteca/admin/instagram/api/queue/${it.id}`,
                                {
                                  method: "PATCH",
                                  headers: { "Content-Type": "application/json" },
                                  body: JSON.stringify({ media_type: nuevo }),
                                },
                              );
                              window.location.reload();
                            }}
                            className="bg-transparent border border-divider focus:border-accent outline-none text-ink text-xs font-mono px-2 py-1.5"
                          >
                            <option value="IMAGE">Foto única</option>
                            <option value="CAROUSEL">Carrusel</option>
                            <option value="REELS">Reel (vídeo)</option>
                          </select>
                          <span className="font-mono text-[9px] text-ink-faint">
                            al cambiarlo hay que «re-preparar»
                          </span>
                        </div>
                      </div>

                      <div className="mt-4 pt-4 border-t border-divider">
                        <ProgramarPost
                          itemId={it.id}
                          publishAt={scheduleOf(it)}
                          publishOn={it.publish_on}
                          disabled={busy !== null}
                          onSaved={(nuevo) =>
                            setSchedules((prev) => ({ ...prev, [it.id]: nuevo }))
                          }
                        />
                      </div>
                    </>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </>
    );
  }

  function ItemActions({ it }: { it: IGItem }) {
    if (it.status === "published" || it.status === "discarded") return null;
    return (
      <div className="shrink-0 flex items-center gap-2 flex-wrap">
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
            title={account.ok ? "" : "El token de IG no es válido"}
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
      </div>
    );
  }

  return (
    <div className="space-y-14">
      {/* ---------- Propuestas evergreen (aprobación en bloque) ---------- */}
      {proposed.length > 0 && (
        <section>
          <h2 className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-1">
            Propuestas evergreen · {proposed.length}
          </h2>
          <p className="font-serif italic text-ink-dim text-sm mb-4">
            Material intemporal sacado del corpus (frases, efemérides, anécdotas
            y citas). Marca las que te gusten y apruébalas en bloque: se les
            generará imagen + caption y pasarán a la cola.
          </p>
          <div className="flex items-center gap-3 flex-wrap mb-4">
            <button
              type="button"
              onClick={toggleSelectAll}
              data-cursor="hover"
              className="font-mono text-[10px] tracking-[2px] uppercase border border-divider hover:border-accent hover:text-accent text-ink-dim px-3 py-1.5"
            >
              {selected.size === proposed.length ? "deseleccionar todo" : "seleccionar todo"}
            </button>
            <button
              type="button"
              disabled={busy !== null || selected.size === 0}
              onClick={bulkApprove}
              data-cursor="hover"
              className="font-mono text-[10px] tracking-[2px] uppercase border border-accent text-accent hover:bg-accent hover:text-white px-3 py-1.5 disabled:opacity-40"
            >
              {busy !== null
                ? "procesando… (genera imagen+caption)"
                : `✓ aprobar seleccionadas (${selected.size})`}
            </button>
            <button
              type="button"
              disabled={busy !== null || selected.size === 0}
              onClick={bulkDiscard}
              data-cursor="hover"
              className="font-mono text-[10px] tracking-[2px] uppercase border border-divider hover:border-divider-strong text-ink-faint hover:text-ink px-3 py-1.5 disabled:opacity-40"
            >
              ✕ descartar seleccionadas
            </button>
          </div>
          <ul className="divide-y divide-divider">
            {proposed.map((it) => (
              <li key={it.id} className="py-4">
                <div className="flex items-start gap-3">
                  <input
                    type="checkbox"
                    checked={selected.has(it.id)}
                    onChange={() => toggleSelected(it.id)}
                    data-cursor="hover"
                    className="mt-1.5 accent-accent w-4 h-4 shrink-0"
                  />
                  <div className="flex-1 min-w-0">
                    <p className="font-mono text-[9px] tracking-[2px] uppercase text-ink-faint mb-1">
                      <span className="text-accent">
                        {CONTENT_TYPE_LABEL[it.content_type] ?? it.content_type}
                      </span>
                      {it.publish_on && (
                        <span className="text-accent"> · 📅 {fmtDate(it.publish_on)}</span>
                      )}
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
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* ---------- Cola de publicación (arrastrable) ---------- */}
      {upcoming.length > 0 && (
        <section>
          <div className="flex items-center justify-between gap-3 flex-wrap mb-1">
            <h2 className="font-mono text-[10px] tracking-[3px] uppercase text-accent">
              Próximas publicaciones · {upcoming.length}
            </h2>
            <button
              type="button"
              disabled={busy !== null}
              onClick={interleave}
              data-cursor="hover"
              title="Reordena la cola intercalando los tipos para que el goteo salga variado"
              className="font-mono text-[10px] tracking-[2px] uppercase border border-divider hover:border-accent hover:text-accent text-ink-dim px-3 py-1.5 disabled:opacity-40"
            >
              ⇄ alternar tipos de publicación
            </button>
            <button
              type="button"
              disabled={busy !== null}
              onClick={autoSchedule}
              data-cursor="hover"
              title="Reparte los posts aprobados por las próximas 4 semanas, intercalando tipos y respetando el tope semanal"
              className="font-mono text-[10px] tracking-[2px] uppercase border border-accent text-accent hover:bg-accent hover:text-white px-3 py-1.5 disabled:opacity-40"
            >
              🗓 autoprogramar
            </button>
            <button
              type="button"
              disabled={busy !== null}
              onClick={bulkPrepare}
              data-cursor="hover"
              title="Genera imagen, carrusel o vídeo de todo lo que esté pendiente y sin material"
              className="font-mono text-[10px] tracking-[2px] uppercase border border-accent text-accent hover:bg-accent hover:text-white px-3 py-1.5 disabled:opacity-40"
            >
              ⚙ generar material
            </button>
            <button
              type="button"
              disabled={busy !== null}
              onClick={shuffleFormats}
              data-cursor="hover"
              title="Reparte formatos variados (foto / carrusel / reel) para que el feed no salga monótono. Respeta los que hayas elegido a mano."
              className="font-mono text-[10px] tracking-[2px] uppercase border border-divider hover:border-accent hover:text-accent text-ink-dim px-3 py-1.5 disabled:opacity-40"
            >
              🎲 variar formatos
            </button>
          </div>
          <p className="font-serif italic text-ink-dim text-sm mb-5">
            Goteo de ~11 a la semana. Arrastra para reordenar; el de arriba se
            publica antes. «Autoprogramar» les pone fecha y hora concretas.
          </p>
          <ul className="divide-y divide-divider">
            {upcoming.map((it, index) => (
              <li
                key={it.id}
                onDragOver={(e) => onDragOver(index, e)}
                onDrop={(e) => e.preventDefault()}
                className={`py-5 transition-opacity ${
                  dragIndex === index ? "opacity-40" : ""
                }`}
              >
                <div className="flex items-start gap-3">
                  {/* Solo el asa es arrastrable: así el clic en el título o los
                      botones no se lo traga el drag-and-drop. */}
                  <span
                    aria-hidden
                    draggable={busy === null}
                    onDragStart={() => onDragStart(index)}
                    onDragEnd={persistOrder}
                    data-cursor="hover"
                    className="select-none font-mono text-ink-faint hover:text-accent cursor-grab active:cursor-grabbing pt-1 text-lg leading-none"
                    title="Arrastra para reordenar"
                  >
                    ⠿
                  </span>
                  <div className="flex-1 min-w-0 flex items-start justify-between gap-4 flex-wrap">
                    <div className="flex-1 min-w-0">
                      <ItemMeta it={it} />
                    </div>
                    <ItemActions it={it} />
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* ---------- Efemérides con fecha fija (salen su día) ---------- */}
      {pinned.length > 0 && (
        <section>
          <h2 className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-1">
            Efemérides programadas · {pinned.length}
          </h2>
          <p className="font-serif italic text-ink-dim text-sm mb-5">
            Aniversarios y cumpleaños. Cada uno se publica SOLO el día de su
            efeméride (no entra en el goteo).
          </p>
          <ul className="divide-y divide-divider">
            {pinned.map((it) => (
              <li key={it.id} className="py-4">
                <div className="flex items-start justify-between gap-4 flex-wrap">
                  <div className="flex-1 min-w-0">
                    <p className="font-mono text-[9px] tracking-[2px] uppercase text-accent mb-1">
                      📅 {fmtDate(it.publish_on || "")}
                    </p>
                    <div className="flex-1 min-w-0">
                      <ItemMeta it={it} />
                    </div>
                  </div>
                  <ItemActions it={it} />
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* ---------- Estados terminales (solo lectura) ---------- */}
      {TERMINAL_ORDER.map((s) => {
        const items = byTerminal.get(s) ?? [];
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
                      <ItemMeta it={it} />
                    </div>
                    <ItemActions it={it} />
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
