"use client";

import { useEffect, useState } from "react";
import {
  ActionBar,
  Button,
  Card,
  EmptyState,
  Field,
  JobStatus,
  Notice,
  Section,
  StatusBadge,
  cx,
  inputClass,
} from "@/components/admin/ui";
import { CLIP_STATUS, etiqueta } from "@/lib/admin/labels";

/**
 * Panel de clips de vídeo de terceros.
 *
 * Publicar fragmentos de canales ajenos es una decisión editorial tomada a
 * sabiendas: se hace sin pedir permiso previo y se atienden las reclamaciones
 * si llegan. Por eso esta pantalla enseña siempre la PROCEDENCIA (canal, vídeo,
 * tramo) y tiene el botón de retirada bien a la vista: si alguien reclama, hay
 * que poder responder en minutos.
 *
 * La descarga no la hace el servidor —YouTube bloquea su IP— sino el daemon de
 * la Mac, así que un clip recién pedido tarda unos minutos en estar listo.
 */

type Clip = {
  id: number;
  video_id: string;
  url: string;
  video_title: string | null;
  channel_title: string | null;
  channel_url: string | null;
  start_s: number;
  end_s: number;
  subtitle: string | null;
  status: string;
  url_cdn: string | null;
  duration_s: number | null;
  error: string | null;
  requested_by: string | null;
  ig_media_id: string | null;
  queue_item_id: number | null;
  retired_at: string | null;
  retired_reason: string | null;
  created_at: string;
};

/** "1:23" → 83. También acepta segundos sueltos. */
function aSegundos(valor: string): number | null {
  const v = valor.trim();
  if (!v) return null;
  if (v.includes(":")) {
    const partes = v.split(":").map((p) => Number(p));
    if (partes.some((n) => !Number.isFinite(n))) return null;
    return partes.reduce((acc, n) => acc * 60 + n, 0);
  }
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

export type Asignable = { id: number; title: string };

export default function ClipsPanel({
  asignables = [],
}: {
  /** Publicaciones de la cola a las que se puede enlazar un clip. */
  asignables?: Asignable[];
}) {
  const [clips, setClips] = useState<Clip[]>([]);
  const [cargando, setCargando] = useState(true);
  const [abierto, setAbierto] = useState(false);
  const [url, setUrl] = useState("");
  const [desde, setDesde] = useState("");
  const [hasta, setHasta] = useState("");
  const [subtitulo, setSubtitulo] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Lo que impide pedir el clip, dicho con palabras. Se enseña junto al botón.
  const falta = [
    !url.trim() && "la URL",
    !hasta.trim() && "el final del tramo",
    !subtitulo.trim() && "«de qué va»",
  ].filter(Boolean) as string[];

  async function recargar() {
    setCargando(true);
    try {
      const res = await fetch("/biblioteca/admin/instagram/api/clips");
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? `error ${res.status}`);
      setClips(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "no se pudo cargar");
    } finally {
      setCargando(false);
    }
  }

  useEffect(() => {
    void recargar();
  }, []);

  async function pedir() {
    const s = aSegundos(desde) ?? 0;
    const e = aSegundos(hasta);
    if (e === null) {
      setError("Pon el final del tramo (segundos o m:ss)");
      return;
    }
    // El tema es el título de la publicación del clip, así que es obligatorio.
    if (!subtitulo.trim()) {
      setError("Di de qué va el clip: es el título de su publicación");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/biblioteca/admin/instagram/api/clips", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url,
          start_s: s,
          end_s: e,
          subtitle: subtitulo.trim(),
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? `error ${res.status}`);
      setUrl("");
      setDesde("");
      setHasta("");
      setSubtitulo("");
      await recargar();
    } catch (err) {
      setError(err instanceof Error ? err.message : "no se pudo pedir");
    } finally {
      setBusy(false);
    }
  }

  async function asignar(clip: Clip) {
    if (asignables.length === 0) {
      window.alert("No hay publicaciones en la cola a las que enlazarlo.");
      return;
    }
    const lista = asignables
      .slice(0, 25)
      .map((a, i) => `${i + 1}. ${a.title.slice(0, 58)}`)
      .join("\n");
    const eleccion = window.prompt(
      `¿En qué publicación va este clip?\n\n${lista}\n\nEscribe el número:`,
    );
    if (!eleccion) return;
    const idx = Number(eleccion) - 1;
    if (!Number.isInteger(idx) || idx < 0 || idx >= asignables.length) {
      window.alert("Número no válido");
      return;
    }
    setBusy(true);
    try {
      const res = await fetch(
        `/biblioteca/admin/instagram/api/clips/${clip.id}/assign`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ queue_item_id: asignables[idx].id }),
        },
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? `error ${res.status}`);
      window.alert(
        `Enlazado con «${asignables[idx].title.slice(0, 50)}».\n\n` +
          "Ese post pasa a formato «clip externo» y hay que prepararlo para que lo use.",
      );
      await recargar();
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "no se pudo enlazar");
    } finally {
      setBusy(false);
    }
  }

  async function retirar(clip: Clip) {
    const motivo = window.prompt(
      `Retirar el clip de «${clip.channel_title ?? "canal desconocido"}».\n\n` +
        "Se borra el post de Instagram y el fichero de Cloudinary.\n" +
        "¿Motivo? (queda registrado)",
    );
    if (!motivo) return;
    setBusy(true);
    try {
      const res = await fetch(
        `/biblioteca/admin/instagram/api/clips/${clip.id}/retire`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ reason: motivo }),
        },
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? `error ${res.status}`);
      await recargar();
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "no se pudo retirar");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="border-t border-divider pt-10">
      <Section
        title="Clips de vídeo"
        count={clips.length}
        help="Fragmentos de YouTube para publicar como reel. Los baja el ordenador de casa (YouTube bloquea al servidor), así que tardan unos minutos en estar listos. La procedencia se enseña siempre: si alguien reclama, se retira en un paso."
        actions={
          <Button variant={abierto ? "ghost" : "primary"} onClick={() => setAbierto((a) => !a)}>
            {abierto ? "Cerrar" : "＋ Pedir un clip"}
          </Button>
        }
      >
        {abierto && (
          <Card className="mb-6 max-w-2xl space-y-4">
            <Field label="Enlace del vídeo" htmlFor="clip-url">
              <input
                id="clip-url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://youtu.be/…"
                className={cx(inputClass, "font-mono")}
              />
            </Field>
            <div className="flex flex-wrap gap-3">
              <Field label="Desde" htmlFor="clip-desde">
                <input
                  id="clip-desde"
                  value={desde}
                  onChange={(e) => setDesde(e.target.value)}
                  placeholder="0:30"
                  className={cx(inputClass, "w-24 font-mono")}
                />
              </Field>
              <Field label="Hasta" htmlFor="clip-hasta">
                <input
                  id="clip-hasta"
                  value={hasta}
                  onChange={(e) => setHasta(e.target.value)}
                  placeholder="0:52"
                  className={cx(inputClass, "w-24 font-mono")}
                />
              </Field>
            </div>
            {/*
              El ejemplo va con «p. ej.» delante a propósito: sin eso parecía
              un campo ya relleno, y como es obligatorio el botón se quedaba
              apagado sin que se viera por qué.
            */}
            <Field
              label="De qué va (obligatorio)"
              htmlFor="clip-tema"
              hint="Es el título de su publicación en la cola."
            >
              <input
                id="clip-tema"
                value={subtitulo}
                onChange={(e) => setSubtitulo(e.target.value)}
                placeholder="p. ej. Concierto de Extremoduro en la sala Vértigo, 1993"
                className={cx(inputClass, "placeholder:italic")}
              />
            </Field>
            <div className="flex flex-wrap items-center gap-3">
              <Button variant="primary" disabled={busy || falta.length > 0} loading={busy} onClick={pedir}>
                Pedir clip
              </Button>
              {/*
                Un botón apagado sin explicación es un callejón sin salida: el
                placeholder de «de qué va» parecía un valor puesto y no había forma
                de saber qué faltaba. Ahora se dice.
              */}
              <span className="text-sm">
                {falta.length > 0 ? (
                  <span className="text-warn">Falta {falta.join(" y ")}.</span>
                ) : (
                  <span className="text-ink-faint">
                    Máximo 60 s · nada de canales oficiales ni discográficas · entra en la cola
                    como publicación propia.
                  </span>
                )}
              </span>
            </div>
          </Card>
        )}

        {error && (
          <div className="mb-4">
            <Notice onClose={() => setError(null)}>{error}</Notice>
          </div>
        )}

        {cargando ? (
          <p className="text-sm text-ink-faint">Cargando…</p>
        ) : clips.length === 0 ? (
          <EmptyState>Todavía no has pedido ningún clip.</EmptyState>
        ) : (
          <ul className="space-y-3">
            {clips.map((c) => {
              const st = etiqueta(CLIP_STATUS, c.status);
              const enCurso = c.status === "requested" || c.status === "downloading";
              return (
                <Card key={c.id} as="li" tone={st.tone}>
                  <div className="flex flex-wrap items-start gap-4">
                    <div className="flex-1 min-w-[240px]">
                      <div className="flex flex-wrap items-center gap-2">
                        {enCurso ? (
                          <JobStatus label={st.label} hint={st.hint} />
                        ) : (
                          <StatusBadge tone={st.tone} title={st.hint}>
                            {st.label}
                          </StatusBadge>
                        )}
                        <span className="font-mono text-xs text-ink-faint">
                          tramo {Math.round(c.start_s)}–{Math.round(c.end_s)} s
                        </span>
                        {c.ig_media_id && <StatusBadge tone="ok">En Instagram</StatusBadge>}
                      </div>
                      {c.subtitle && <p className="mt-2 text-sm text-ink-dim">{c.subtitle}</p>}
                      <p className="mt-1 font-serif text-ink text-base leading-tight">
                        {c.video_title ?? c.url}
                      </p>
                      {/* La procedencia, siempre visible: es lo que se enseña si
                          alguien reclama. */}
                      <p className="mt-1 text-sm text-ink-dim">
                        Canal:{" "}
                        {c.channel_url ? (
                          <a
                            href={c.channel_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-accent hover:underline"
                          >
                            {c.channel_title ?? "—"}
                          </a>
                        ) : (
                          (c.channel_title ?? "—")
                        )}{" "}
                        ·{" "}
                        <a href={c.url} target="_blank" rel="noopener noreferrer" className="hover:text-accent">
                          Ver original ↗
                        </a>
                      </p>
                      {c.queue_item_id && (
                        <p className="mt-1 text-sm text-info">Va en la publicación #{c.queue_item_id}</p>
                      )}
                      {c.retired_reason && (
                        <p className="mt-1 text-sm text-ink-faint">Retirado: {c.retired_reason}</p>
                      )}
                      {c.error && (
                        <p className="mt-2 font-mono text-xs text-danger break-words">{c.error.slice(0, 200)}</p>
                      )}
                    </div>

                    {c.url_cdn && c.status !== "retired" && (
                      <video
                        src={c.url_cdn}
                        controls
                        playsInline
                        className="w-[150px] h-[266px] object-contain bg-black rounded border border-divider shrink-0"
                      />
                    )}
                  </div>

                  {c.status !== "retired" && (
                    <ActionBar
                      primary={
                        c.status === "ready" && (
                          <Button
                            variant="primary"
                            disabled={busy}
                            onClick={() => asignar(c)}
                            title="Enlaza el clip con una publicación: al prepararla se usará este vídeo, con su sonido"
                          >
                            {c.queue_item_id ? "Cambiar de publicación" : "Usar en una publicación"}
                          </Button>
                        )
                      }
                      danger={
                        <Button
                          variant="danger"
                          disabled={busy}
                          onClick={() => retirar(c)}
                          title="Borra el post de Instagram y el fichero, y deja constancia del motivo"
                        >
                          Retirar
                        </Button>
                      }
                    />
                  )}
                </Card>
              );
            })}
          </ul>
        )}
      </Section>
    </div>
  );
}
