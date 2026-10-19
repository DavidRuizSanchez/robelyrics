"use client";

import { useState } from "react";
import type { IGAccount, IGItem, IGNewsCandidate } from "./page";
import InstagramPreview, { type PreviewMedia } from "./InstagramPreview";
import Term from "@/components/admin/Term";
import {
  ActionBar,
  Button,
  Callout,
  Card,
  Data,
  Details,
  EmptyState,
  Eyebrow,
  Notice,
  Section,
  StatusBadge,
  cx,
  inputClass,
} from "@/components/admin/ui";
import { IG_CONTENT_TYPE, IG_STATUS, etiqueta, type Tone } from "@/lib/admin/labels";
import ProgramarPost from "./ProgramarPost";

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
    evidence?: Evidencia | null;
  } | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [draftCaption, setDraftCaption] = useState("");
  const [savedFlash, setSavedFlash] = useState(false);
  // Error de la última acción (sustituye a los alert de error).
  const [error, setError] = useState<string | null>(null);

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
        setError(data.error || `Error ${res.status}`);
        return;
      }
      window.location.reload();
    } catch (e) {
      setError(`Error de red: ${e}`);
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

  function bulkApprove(soloEstas?: number[]) {
    const ids = soloEstas ?? [...selected];
    if (ids.length === 0) return;
    if (
      !window.confirm(
        ids.length === 1
          ? "¿Aprobar esta propuesta? Entra en la cola de publicación (si le falta, se le genera imagen y texto)."
          : `¿Aprobar ${ids.length} propuestas? Entran en la cola de publicación (si les falta, se les genera imagen y texto).`,
      )
    )
      return;
    call("POST", "/biblioteca/admin/instagram/api/queue/bulk/approve", { ids });
  }

  function bulkDiscard(soloEstas?: number[]) {
    const ids = soloEstas ?? [...selected];
    if (ids.length === 0) return;
    if (!window.confirm(ids.length === 1 ? "¿Descartar esta propuesta?" : `¿Descartar ${ids.length} propuestas?`))
      return;
    call("POST", "/biblioteca/admin/instagram/api/queue/bulk/discard", { ids });
  }

  function interleave() {
    if (!window.confirm("¿Reordenar la cola intercalando los tipos de publicación?")) return;
    call("POST", "/biblioteca/admin/instagram/api/queue/interleave");
  }

  // --- Generar posts que enseñan la web ---
  // Las piezas se componen consultando la API de verdad, así que cada vez que
  // se pulsa salen con una pregunta y unos versos nuevos.
  async function generateProduct() {
    if (
      !window.confirm(
        "¿Generar publicaciones que enseñen la web?\n\n" +
          "Se consulta el consultorio y el buscador de verdad para componer las " +
          "piezas con contenido real, y entran en la cola como propuestas.",
      )
    )
      return;
    await call(
      "POST",
      "/biblioteca/admin/instagram/api/queue/generate-product",
    );
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
        // Re-sincroniza con el servidor: el aviso se perdería con la recarga,
        // así que aquí se mantiene el alert.
        alert(data.error || `Error ${res.status}`);
        window.location.reload();
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
        setError(d.error || `Error ${res.status}`);
        setExpandedId(null);
        return;
      }
      const data = await res.json();
      setDetail({
        caption: data.caption ?? null,
        image_b64: data.image_b64 ?? null,
        image_url: data.image_url ?? null,
        // Sin esto la preview nunca recibía las piezas, y un reel se veía como
        // «vídeo por generar» aunque estuviera generado y servido bien.
        media: data.media ?? [],
        // La API la manda desde que existe el panel de procedencia, pero aquí
        // no se copiaba: la ficha «de dónde sale cada cosa» no se veía nunca.
        evidence: data.evidence ?? null,
      });
      setDraftCaption(data.caption ?? "");
    } catch (e) {
      setError(`Error de red: ${e}`);
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
        setError(d.error || `Error ${res.status}`);
        return;
      }
      const data = await res.json();
      // Se conservan las piezas y la evidencia: sin ellas, guardar el caption
      // dejaba un reel ya generado como «vídeo por generar» en la preview.
      setDetail((prev) => ({
        caption: data.caption ?? null,
        image_b64: data.image_b64 ?? null,
        image_url: data.image_url ?? null,
        media: data.media ?? prev?.media ?? [],
        evidence: data.evidence ?? prev?.evidence ?? null,
      }));
      setSavedFlash(true);
    } catch (e) {
      setError(`Error de red: ${e}`);
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

  const sinMaterial = upcoming.filter((it) => !it.is_prepared).length;
  const porRevisar = queue.filter(
    (it) => it.needs_human && it.status !== "published" && it.status !== "discarded",
  ).length;

  // ── Piezas de una fila ────────────────────────────────────────────────────
  // Funciones de render, NO componentes: definidas aquí dentro, un componente
  // sería un tipo nuevo en cada render y React remontaría la fila, así que el
  // textarea del caption perdía el foco a cada tecla.

  function renderItem(it: IGItem) {
    const st = etiqueta(IG_STATUS, it.status);
    const cuando = scheduleOf(it);
    const foto = it.is_prepared ? etiquetaFoto(it) : null;
    return (
      <>
        <div className="flex flex-wrap items-start justify-between gap-2">
          <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-ink-dim">
            <span>{IG_CONTENT_TYPE[it.content_type] ?? (it.is_blog ? "Blog" : it.category ?? "Actualidad")}</span>
            <span className="text-ink-faint">· {formatoDe(it)}</span>
            {it.source_name && <span className="text-ink-faint">· {it.source_name}</span>}
          </p>
          <div className="flex flex-wrap gap-1.5">
            <StatusBadge tone={st.tone} title={st.hint}>
              {st.label}
            </StatusBadge>
            {cuando && (
              <StatusBadge tone="info">
                Sale el{" "}
                {new Date(cuando).toLocaleString("es-ES", {
                  day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
                  timeZone: "Europe/Madrid",
                })}
              </StatusBadge>
            )}
            {!cuando && it.publish_on && (
              <StatusBadge tone="info">Sale el {fmtDate(it.publish_on)}</StatusBadge>
            )}
          </div>
        </div>

        <button
          type="button"
          onClick={() => toggleDetail(it.id)}
          aria-expanded={expandedId === it.id}
          className="mt-1 text-left font-serif text-lg text-ink leading-tight hover:text-accent transition-colors rounded focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
        >
          {it.title}
        </button>
        {it.summary && <Resumen texto={it.summary} />}

        {it.needs_human && (
          <Callout tone="warn" className="mt-3" title="Necesita que lo mires">
            Una guarda no pudo confirmar algo (la identidad, la foto o una afirmación). Ábrelo
            para ver qué y apruébalo tú: <Term k="needsHuman">no sale en bloque</Term>.
          </Callout>
        )}
        {it.error && (
          <Callout tone="danger" className="mt-3" title="Último intento fallido">
            <span className="font-mono text-xs break-words">{it.error}</span>
          </Callout>
        )}

        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
          {foto && (
            <span className={cx("inline-flex items-center gap-1", toneClass(foto.tone))} title={it.photo_verdict ?? undefined}>
              {foto.label}
            </span>
          )}
          {it.is_prepared ? (
            <span className="text-ok">✓ Material listo</span>
          ) : (
            it.status !== "published" &&
            it.status !== "discarded" && <span className="text-ink-faint">Sin material todavía</span>
          )}
          {it.has_caption && <span className="text-ink-faint">✓ Texto escrito</span>}
          <button
            type="button"
            onClick={() => toggleDetail(it.id)}
            className="text-accent hover:underline"
          >
            {expandedId === it.id ? "Ocultar ▲" : "Ver y editar ▼"}
          </button>
          {it.ig_media_id && (
            <a
              href={`https://www.instagram.com/p/${it.ig_media_id}/`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-accent hover:underline"
            >
              Ver en Instagram ↗
            </a>
          )}
          {it.source_url && (
            <a
              href={it.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-ink-dim hover:text-accent"
            >
              Fuente ↗
            </a>
          )}
        </div>

        {expandedId === it.id && (
          <div className="mt-4 rounded-md border border-divider bg-bg/60 p-4">
            {detailLoading ? (
              <p className="text-sm text-ink-faint">Cargando…</p>
            ) : (
              <div className="flex flex-col lg:flex-row gap-6">
                {/* Vista previa fiel al feed: imagen + caption con su corte
                    real. Es donde se ve si la primera línea dice algo. */}
                <InstagramPreview
                  imageSrc={
                    detail?.image_b64
                      ? `data:image/jpeg;base64,${detail.image_b64}`
                      : detail?.image_url ?? null
                  }
                  caption={it.status === "published" ? detail?.caption ?? "" : draftCaption}
                  media={detail?.media ?? []}
                  mediaSrc={(pos) => `/biblioteca/admin/instagram/api/queue/${it.id}/media/${pos}`}
                  formatoPedido={it.media_type}
                />

                <div className="flex-1 min-w-0 space-y-6">
                  {detail?.evidence && <EvidenciaPost ev={detail.evidence} />}

                  {/* Editor del caption */}
                  <div>
                    <label htmlFor={`caption-${it.id}`} className="text-sm font-medium text-ink-dim">
                      Texto del post
                    </label>
                    {it.status === "published" ? (
                      <p className="mt-1 font-serif text-sm text-ink-dim whitespace-pre-wrap">
                        {detail?.caption || "(sin texto)"}
                      </p>
                    ) : (
                      <>
                        <textarea
                          id={`caption-${it.id}`}
                          value={draftCaption}
                          onChange={(e) => {
                            setDraftCaption(e.target.value);
                            setSavedFlash(false);
                          }}
                          rows={8}
                          className={cx(inputClass, "mt-1 font-serif leading-relaxed resize-y")}
                        />
                        <div className="mt-2 flex flex-wrap items-center gap-3">
                          <Button
                            size="sm"
                            variant="primary"
                            disabled={busy !== null || draftCaption === (detail?.caption ?? "")}
                            loading={busy === "save"}
                            onClick={() => saveCaption(it.id)}
                          >
                            Guardar texto
                          </Button>
                          {savedFlash && <span className="text-sm text-ok">Guardado ✓</span>}
                          <span className="font-mono text-xs text-ink-faint">
                            {draftCaption.length} caracteres
                          </span>
                        </div>
                        <p className="mt-2 text-xs text-warn">
                          Ojo: «rehacer material» vuelve a escribir el texto y la imagen desde cero y
                          pierde esta edición. Edita justo antes de publicar.
                        </p>

                        <div className="mt-5 border-t border-divider pt-4">
                          <p className="text-sm font-medium text-ink-dim">Formato</p>
                          {/*
                            Un post de clip o de «la web» NO cambia de formato: su
                            formato ES su tema. Ofrecerlo en el desplegable dejaba
                            convertir una noticia en «clip externo» y el post se
                            quedaba esperando un vídeo que nunca iba a tener.
                          */}
                          {it.content_type === "clip" || it.content_type === "product" ? (
                            <p className="mt-1 text-sm text-ink-dim">
                              {it.content_type === "clip"
                                ? "🎬 Clip externo: el vídeo es el tema de este post, así que el formato no se cambia."
                                : "✦ Funcionalidad de la web: la consulta es el tema de este post, así que el formato no se cambia."}
                            </p>
                          ) : (
                            <div className="mt-1 flex flex-wrap items-center gap-2">
                              <select
                                aria-label="Formato del post"
                                value={it.media_type || "IMAGE"}
                                disabled={busy !== null}
                                onChange={async (e) => {
                                  const nuevo = e.target.value;
                                  await fetch(`/biblioteca/admin/instagram/api/queue/${it.id}`, {
                                    method: "PATCH",
                                    headers: { "Content-Type": "application/json" },
                                    body: JSON.stringify({ media_type: nuevo }),
                                  });
                                  window.location.reload();
                                }}
                                className={cx(inputClass, "w-auto")}
                              >
                                <option value="IMAGE">Foto única</option>
                                <option value="CAROUSEL">Carrusel</option>
                                <option value="REELS">Reel · verso animado</option>
                              </select>
                              <span className="text-xs text-ink-faint">
                                Al cambiarlo hay que rehacer el material.
                              </span>
                            </div>
                          )}
                        </div>

                        <div className="mt-5 border-t border-divider pt-4">
                          <ProgramarPost
                            itemId={it.id}
                            publishAt={scheduleOf(it)}
                            publishOn={it.publish_on}
                            disabled={busy !== null}
                            onSaved={(nuevo) => setSchedules((prev) => ({ ...prev, [it.id]: nuevo }))}
                          />
                        </div>
                      </>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </>
    );
  }

  function renderActions(it: IGItem) {
    if (it.status === "published" || it.status === "discarded") return null;
    return (
      <ActionBar
        primary={
          it.is_prepared ? (
            <Button
              variant="primary"
              disabled={busy !== null || !account.ok}
              onClick={() => publish(it.id, false)}
              title={account.ok ? "" : "La conexión con Instagram no funciona"}
            >
              ▶ Publicar ahora
            </Button>
          ) : (
            <Button variant="primary" disabled={busy !== null} onClick={() => prepare(it.id)}>
              Preparar material
            </Button>
          )
        }
        secondary={
          it.is_prepared && (
            <Button
              size="sm"
              variant="ghost"
              disabled={busy !== null}
              onClick={() => prepare(it.id)}
              title="Vuelve a generar imagen y texto desde cero (cuesta dinero y pierde tus ediciones)"
            >
              ↻ Rehacer material
            </Button>
          )
        }
        danger={
          <Button variant="danger" disabled={busy !== null} onClick={() => discard(it.id)}>
            Descartar
          </Button>
        }
      />
    );
  }

  return (
    <div className="space-y-12">
      {error && <Notice onClose={() => setError(null)}>{error}</Notice>}

      {porRevisar > 0 && (
        <Callout tone="warn" title={`${porRevisar} post${porRevisar === 1 ? "" : "s"} necesita${porRevisar === 1 ? "" : "n"} que lo mires`}>
          Están marcados con «Necesita que lo mires». Ábrelos uno a uno: no se aprueban en bloque.
        </Callout>
      )}

      {/* ---------- Propuestas evergreen (aprobación en bloque) ---------- */}
      {proposed.length > 0 && (
        <Section
          title="Propuestas por aprobar"
          count={proposed.length}
          help="Material intemporal sacado del corpus: frases, efemérides, anécdotas y citas. Marca las que te gusten y apruébalas: se les genera imagen y texto y pasan a la cola."
          actions={
            <>
              <Button size="sm" variant="ghost" onClick={toggleSelectAll}>
                {selected.size === proposed.length ? "Quitar selección" : "Seleccionar todas"}
              </Button>
              <Button
                variant="primary"
                disabled={busy !== null || selected.size === 0}
                loading={busy !== null && selected.size > 0}
                loadingLabel="Generando imagen y texto…"
                onClick={() => bulkApprove()}
              >
                ✓ Aprobar ({selected.size})
              </Button>
              <Button
                variant="danger"
                disabled={busy !== null || selected.size === 0}
                onClick={() => bulkDiscard()}
              >
                Descartar ({selected.size})
              </Button>
            </>
          }
        >
          <ul className="space-y-2">
            {proposed.map((it) => (
              <Card key={it.id} as="li" tone={toneFila(it)}>
                <div className="flex items-start gap-3">
                  <input
                    type="checkbox"
                    checked={selected.has(it.id)}
                    onChange={() => toggleSelected(it.id)}
                    aria-label={`Seleccionar «${it.title}»`}
                    className="mt-1.5 h-4 w-4 shrink-0 accent-accent"
                  />
                  <div className="flex-1 min-w-0">
                    {renderItem(it)}
                    <ActionBar
                      primary={
                        <Button variant="primary" disabled={busy !== null} onClick={() => bulkApprove([it.id])}>
                          ✓ Aprobar
                        </Button>
                      }
                      danger={
                        <Button variant="danger" disabled={busy !== null} onClick={() => bulkDiscard([it.id])}>
                          Descartar
                        </Button>
                      }
                    />
                  </div>
                </div>
              </Card>
            ))}
          </ul>
        </Section>
      )}

      {/* ---------- Cola de publicación (arrastrable) ---------- */}
      {upcoming.length > 0 && (
        <Section
          title="Próximas publicaciones"
          count={upcoming.length}
          help="Salen solas, unas 11 por semana, en este orden: arrastra con el asa ⠿ para cambiarlo. «Programar automáticamente» les pone día y hora."
        >
          <div className="mb-4 rounded-md border border-divider bg-paper p-3">
            <div className="flex flex-wrap items-center gap-2">
              <Button variant="primary" disabled={busy !== null} onClick={autoSchedule}>
                🗓 Programar automáticamente
              </Button>
              <Button
                disabled={busy !== null || sinMaterial === 0}
                onClick={bulkPrepare}
                title="Genera imagen, carrusel o vídeo de lo que está en cola sin material (tiene coste)"
              >
                ⚙ Generar material pendiente ({sinMaterial})
              </Button>
            </div>
            <Details summary="Más herramientas de la cola" className="mt-3">
              <ul className="space-y-2 text-sm">
                <li className="flex flex-wrap items-center gap-2">
                  <Button size="sm" disabled={busy !== null} onClick={shuffleFormats}>
                    🎲 Variar formatos
                  </Button>
                  <span className="text-ink-dim">Reparte foto, carrusel y reel para que el feed no sea monótono. Respeta lo que elegiste a mano.</span>
                </li>
                <li className="flex flex-wrap items-center gap-2">
                  <Button size="sm" disabled={busy !== null} onClick={interleave}>
                    ⇄ Intercalar tipos
                  </Button>
                  <span className="text-ink-dim">Reordena para que no salgan seguidas dos cosas del mismo tipo.</span>
                </li>
                <li className="flex flex-wrap items-center gap-2">
                  <Button size="sm" disabled={busy !== null} onClick={generateProduct}>
                    ✦ Crear posts sobre la web
                  </Button>
                  <span className="text-ink-dim">Consulta el consultorio y el buscador de verdad y propone piezas que enseñan la web.</span>
                </li>
              </ul>
            </Details>
          </div>
          <ul className="space-y-3">
            {upcoming.map((it, index) => (
              <li
                key={it.id}
                onDragOver={(e) => onDragOver(index, e)}
                onDrop={(e) => e.preventDefault()}
                className={cx("transition-opacity", dragIndex === index && "opacity-40")}
              >
                <Card tone={toneFila(it)}>
                  <div className="flex items-start gap-3">
                    {/* Solo el asa es arrastrable: así el clic en el título o los
                        botones no se lo traga el drag-and-drop. */}
                    <span
                      draggable={busy === null}
                      onDragStart={() => onDragStart(index)}
                      onDragEnd={persistOrder}
                      className="select-none text-ink-faint hover:text-accent cursor-grab active:cursor-grabbing pt-0.5 text-lg leading-none"
                      title="Arrastra para reordenar"
                      aria-label={`Posición ${index + 1}. Arrastra para reordenar`}
                    >
                      ⠿
                    </span>
                    <span className="pt-0.5 font-mono text-xs text-ink-faint w-5 shrink-0">{index + 1}</span>
                    <div className="flex-1 min-w-0">
                      {renderItem(it)}
                      {renderActions(it)}
                    </div>
                  </div>
                </Card>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {/* ---------- Con fecha fija (salen su día) ---------- */}
      {pinned.length > 0 && (
        <Section
          title="Con fecha fija"
          count={pinned.length}
          help="Efemérides y posts programados a mano. Cada uno sale su día y hora; no entran en el goteo."
        >
          <ul className="space-y-3">
            {pinned.map((it) => (
              <Card key={it.id} as="li" tone={toneFila(it)}>
                {renderItem(it)}
                {renderActions(it)}
              </Card>
            ))}
          </ul>
        </Section>
      )}

      {/* ---------- Estados terminales (solo lectura) ---------- */}
      {TERMINAL_ORDER.map((s) => {
        const items = byTerminal.get(s) ?? [];
        if (items.length === 0) return null;
        const st = etiqueta(IG_STATUS, s);
        const lista = (
          <ul className="space-y-3">
            {items.map((it) => (
              <Card key={it.id} as="li" tone={s === "failed" ? "danger" : "neutral"}>
                {renderItem(it)}
                {renderActions(it)}
              </Card>
            ))}
          </ul>
        );
        // Lo fallido se ve abierto (hay que actuar); lo publicado y descartado, plegado.
        return s === "failed" ? (
          <Section
            key={s}
            title="Fallidas"
            count={items.length}
            help="Instagram las rechazó o no se pudieron preparar. Se reintentan solas mientras les queden intentos; si no, rehaz el material o descártalas."
          >
            {lista}
          </Section>
        ) : (
          <section key={s}>
            <Details
              summary={
                <span className="text-base text-ink-dim">
                  {st.label}s <span className="font-mono text-ink-faint">{items.length}</span>
                </span>
              }
            >
              {lista}
            </Details>
          </section>
        );
      })}

      {queue.length === 0 && (
        <EmptyState>
          La cola está vacía. Encola alguna noticia desde el banco de abajo o espera al proceso
          diario.
        </EmptyState>
      )}

      {/* ---------- Banco de noticias para encolar ---------- */}
      <Section
        title="Noticias para encolar"
        count={candidates.length}
        help="Lo mejor del último repaso del agregador de noticias. Las que ya están en la cola no se pueden volver a encolar."
      >
        {candidates.length === 0 ? (
          <EmptyState>No hay noticias en el almacén. Hace falta pasar antes el agregador.</EmptyState>
        ) : (
          <ul className="divide-y divide-divider rounded-md border border-divider">
            {candidates.map((n) => {
              const ya = candidateIdsInQueue.has(n.id);
              return (
                <li key={n.id} className="flex flex-wrap items-start justify-between gap-3 p-3">
                  <div className="flex-1 min-w-0">
                    <p className="flex flex-wrap items-center gap-x-2 text-sm text-ink-dim">
                      <span>{n.category ?? "Actualidad"}</span>
                      <span className="text-ink-faint">· {n.source_medium ?? n.source_name}</span>
                      <span className="text-ink-faint" title="Puntuación de relevancia del agregador">
                        · relevancia <Data className="text-ink-dim">{n.relevance_score.toFixed(1)}</Data>
                      </span>
                      {n.policy === "ig-only" && <StatusBadge>solo Instagram</StatusBadge>}
                    </p>
                    <p className="mt-0.5 font-serif text-base text-ink leading-tight">{n.title}</p>
                    <a
                      href={n.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm text-ink-dim hover:text-accent"
                    >
                      Ver original ↗
                    </a>
                  </div>
                  {ya ? (
                    <StatusBadge tone="ok">Ya en la cola</StatusBadge>
                  ) : (
                    <Button size="sm" disabled={busy !== null} onClick={() => enqueueNews(n.id)}>
                      ＋ Encolar
                    </Button>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </Section>
    </div>
  );
}

type Evidencia = {
  material_url: string | null;
  material_status: string | null;
  material_chars: number;
  entities: Array<{
    surface: string; kind: string; role: string; status: string;
    label: string | null; description: string | null; qid: string | null;
    context: string; reason: string;
    candidates?: Array<{ qid: string; label: string; description: string }>;
  }>;
  subject_label: string | null;
  subject_qid: string | null;
  subject_description: string | null;
  photo_source: string | null;
  photo_verdict: string | null;
  photo_reason: string | null;
  photo_query: string | null;
  photo_page_url: string | null;
  photo_site: string | null;
  photo_evidence: string[];
  claims: Array<{ claim: string; verdict: string; evidence?: string }>;
  avisos: string[];
};

// El resumen de un clip llega como una ristra «Vídeo de una canción: … Momento: …
// Canción: … AVISO: …». Se parte por esas etiquetas para leerlo campo a campo.
const CAMPOS_RESUMEN = [
  "Vídeo de una canción",
  "Vídeo",
  "Momento",
  "Canción",
  "Verso (de nuestra letra)",
  "Concierto",
  "Canal",
  "Verificado",
  "AVISO",
];

function partirResumen(texto: string): { campo: string; valor: string }[] {
  const alternativas = CAMPOS_RESUMEN.map((c) => c.replace(/[()]/g, "\\$&")).join("|");
  const re = new RegExp(`(?:^|\\s)(${alternativas}):\\s`, "g");
  const marcas = [...texto.matchAll(re)];
  if (marcas.length < 2) return [];
  return marcas.map((m, i) => {
    const inicio = (m.index ?? 0) + m[0].length;
    const fin = i + 1 < marcas.length ? marcas[i + 1].index ?? texto.length : texto.length;
    return { campo: m[1], valor: texto.slice(inicio, fin).trim() };
  });
}

function Resumen({ texto }: { texto: string }) {
  const campos = partirResumen(texto);
  if (campos.length === 0) {
    return (
      <p className="mt-1 font-serif italic text-ink-dim text-sm leading-relaxed line-clamp-2">{texto}</p>
    );
  }
  return (
    <dl className="mt-2 grid gap-x-4 gap-y-1 text-sm sm:grid-cols-[max-content_1fr]">
      {campos.map(({ campo, valor }) =>
        campo === "AVISO" ? (
          <div key={campo} className="sm:col-span-2">
            <Callout tone="warn">{valor}</Callout>
          </div>
        ) : (
          <div key={campo} className="contents">
            <dt className="text-ink-faint">{campo === "Verso (de nuestra letra)" ? "Verso" : campo}</dt>
            <dd className="text-ink-dim">{valor}</dd>
          </div>
        ),
      )}
    </dl>
  );
}

function toneClass(t: Tone): string {
  return { ok: "text-ok", warn: "text-warn", danger: "text-danger", info: "text-info", neutral: "text-ink-dim", accent: "text-accent" }[t];
}

function toneFila(it: IGItem): Tone {
  if (it.error || it.status === "failed") return "danger";
  if (it.needs_human) return "warn";
  return etiqueta(IG_STATUS, it.status).tone;
}

function formatoDe(it: IGItem): string {
  switch (it.media_type) {
    case "CAROUSEL":
      return `carrusel de ${it.media_count}`;
    case "REELS":
      return "reel";
    case "CLIP":
      return "clip externo";
    case "PRODUCT":
      return "pieza sobre la web";
    default:
      return "foto";
  }
}

/**
 * De dónde salió cada cosa del post.
 *
 * Va AL LADO del preview y no dentro: el preview reproduce el feed tal cual, y
 * ensuciarlo le quitaría lo único que sirve para ver si la primera línea dice
 * algo.
 *
 * Esto es lo que faltaba el 17-09-2026: el panel enseñaba la foto compuesta, el
 * caption y «imagen ✓». Para ver que la foto era de otra persona había que
 * reconocer la cara y luego abrir la noticia original a mano.
 */
function EvidenciaPost({ ev }: { ev: Evidencia }) {
  return (
    <div className="space-y-4 rounded-md border border-divider p-3">
      <p className="font-medium text-ink">De dónde sale cada cosa</p>
      {ev.avisos.length > 0 && (
        <Callout tone="warn" title="Revisar">
          <ul className="list-disc pl-5 space-y-1">
            {ev.avisos.map((a, i) => (
              <li key={i}>{a}</li>
            ))}
          </ul>
        </Callout>
      )}

      <div>
        <Eyebrow>Quién es quién</Eyebrow>
        {ev.entities.length === 0 && <p className="mt-1 text-sm text-ink-faint">Sin personas ni entidades.</p>}
        <ul className="mt-1 space-y-1.5">
          {ev.entities.map((e, i) => {
            const ok = e.status === "corpus" || e.status === "wikidata";
            return (
              <li key={i} className="text-sm leading-snug">
                <span className={ok ? "text-ok" : "text-warn"}>{ok ? "✓" : "⚠"}</span>{" "}
                <span className="text-ink">{e.label ?? e.surface}</span>
                {e.description && <span className="text-ink-faint"> · {e.description}</span>}
                {e.qid && (
                  <a
                    href={`https://www.wikidata.org/wiki/${e.qid}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="ml-1 font-mono text-xs text-accent hover:underline"
                  >
                    {e.qid} ↗
                  </a>
                )}
                {(e.status === "ambiguous" || e.status === "unresolved") && (
                  <span className="block text-xs text-ink-faint">
                    No se nombra (no se pudo identificar): {e.reason}
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      </div>

      <div>
        <Eyebrow>La foto</Eyebrow>
        <p className="mt-1 text-sm text-ink">
          {ev.photo_source ? FOTO_ORIGEN[ev.photo_source] ?? ev.photo_source : "—"}
          {ev.photo_verdict && <span className="text-ink-faint"> · {ev.photo_verdict}</span>}
        </p>
        {ev.photo_reason && <p className="text-xs text-ink-faint">{ev.photo_reason}</p>}
        {ev.photo_query && <p className="text-xs text-ink-faint">Se buscó: «{ev.photo_query}»</p>}
        {ev.photo_page_url && (
          <a
            href={ev.photo_page_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-accent hover:underline"
          >
            {ev.photo_site || "De dónde salió"} ↗
          </a>
        )}
      </div>

      {ev.claims.length > 0 && (
        <div>
          <Eyebrow>Lo que afirma el texto</Eyebrow>
          <ul className="mt-1 space-y-1.5">
            {ev.claims.map((c, i) => {
              const ok = c.verdict === "supported";
              return (
                <li key={i} className="text-sm leading-snug">
                  <span className={ok ? "text-ok" : "text-danger"}>{ok ? "✓ Respaldado" : "✗ Sin respaldo"}</span>
                  <span className="text-ink"> · {c.claim}</span>
                  {c.evidence && <span className="block text-xs text-ink-faint">«{c.evidence}»</span>}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      <div>
        <Eyebrow>Material de partida</Eyebrow>
        <p className="mt-1 text-sm text-ink-dim">
          {ev.material_chars > 0
            ? `${ev.material_chars.toLocaleString("es-ES")} caracteres del artículo`
            : "Sin artículo"}
          {ev.material_url && (
            <>
              {" · "}
              <a href={ev.material_url} target="_blank" rel="noopener noreferrer" className="text-accent hover:underline">
                Fuente ↗
              </a>
            </>
          )}
        </p>
      </div>
    </div>
  );
}

const FOTO_ORIGEN: Record<string, string> = {
  ficha_propia: "De nuestra propia ficha",
  wikidata_p18: "Wikimedia Commons (foto oficial de la entidad)",
  google_images: "Búsqueda en la web",
  arte_propio: "Ilustración propia (no retrata a nadie)",
};

/**
 * De dónde salió la foto, en vez del «imagen ✓» de antes.
 *
 * Aquel booleano se enseñó tan campante sobre una foto de Pep Guardiola en una
 * noticia que iba de la presidenta de la Junta de Extremadura: decía que HABÍA
 * imagen, no de quién era. Para cazar el fallo había que reconocer la cara.
 */
function etiquetaFoto(it: IGItem): { label: string; tone: Tone } {
  switch (it.photo_source) {
    case "ficha_propia":
      return { label: "📷 Foto de nuestra ficha", tone: "ok" };
    case "wikidata_p18":
      return { label: "📷 Foto de Commons ✓", tone: "ok" };
    case "google_images":
      return it.photo_verdict === "identidad_sin_mirar"
        ? { label: "📷 Foto de la web · sin comprobar quién es", tone: "warn" }
        : { label: "📷 Foto de la web · identidad comprobada", tone: "ok" };
    case "arte_propio":
      return { label: "🎨 Ilustración propia", tone: "neutral" };
    default:
      return { label: "📷 Imagen generada", tone: "neutral" };
  }
}
