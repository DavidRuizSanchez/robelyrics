"use client";

import { useEffect, useState } from "react";

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

const ESTADO_LABEL: Record<string, string> = {
  requested: "Pedido",
  downloading: "Descargando",
  ready: "Listo",
  published: "Publicado",
  retired: "Retirado",
  failed: "Fallido",
};

const ESTADO_COLOR: Record<string, string> = {
  requested: "border-divider text-ink-dim",
  downloading: "border-accent/50 text-accent/80",
  ready: "border-accent text-accent",
  published: "border-accent bg-accent/10 text-accent",
  retired: "border-divider text-ink-faint line-through",
  failed: "border-red-500/60 text-red-400",
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
          subtitle: subtitulo.trim() || null,
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
          "Ese post pasa a formato reel y hay que prepararlo para que use el clip.",
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
    <section className="mt-16 pt-10 border-t border-divider">
      <div className="flex items-center gap-4 flex-wrap mb-2">
        <h2 className="font-mono text-[11px] tracking-[3px] uppercase text-accent">
          clips de vídeo · {clips.length}
        </h2>
        <button
          type="button"
          onClick={() => setAbierto((a) => !a)}
          data-cursor="hover"
          className="font-mono text-[10px] tracking-[2px] uppercase border border-accent text-accent hover:bg-accent hover:text-white px-3 py-1.5"
        >
          {abierto ? "cerrar" : "+ pedir clip"}
        </button>
      </div>
      <p className="font-serif italic text-ink-dim text-sm mb-5">
        Fragmentos de YouTube para publicar como reel. La descarga la hace el
        daemon de la Mac (la IP del servidor está bloqueada por YouTube), así que
        tarda unos minutos en estar listo.
      </p>

      {abierto && (
        <div className="border border-divider p-4 mb-6 max-w-2xl">
          <label className="font-mono text-[9px] tracking-[2px] uppercase text-ink-faint">
            url del vídeo
          </label>
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://youtu.be/…"
            className="mt-1 w-full bg-transparent border border-divider focus:border-accent outline-none text-ink text-sm font-mono px-2 py-1.5"
          />
          <div className="mt-3 flex gap-3 flex-wrap">
            <div>
              <label className="font-mono text-[9px] tracking-[2px] uppercase text-ink-faint">
                desde
              </label>
              <input
                value={desde}
                onChange={(e) => setDesde(e.target.value)}
                placeholder="0:30"
                className="mt-1 w-24 bg-transparent border border-divider focus:border-accent outline-none text-ink text-sm font-mono px-2 py-1.5"
              />
            </div>
            <div>
              <label className="font-mono text-[9px] tracking-[2px] uppercase text-ink-faint">
                hasta
              </label>
              <input
                value={hasta}
                onChange={(e) => setHasta(e.target.value)}
                placeholder="0:52"
                className="mt-1 w-24 bg-transparent border border-divider focus:border-accent outline-none text-ink text-sm font-mono px-2 py-1.5"
              />
            </div>
            <div className="flex-1 min-w-[200px]">
              <label className="font-mono text-[9px] tracking-[2px] uppercase text-ink-faint">
                texto sobreimpreso (opcional)
              </label>
              <input
                value={subtitulo}
                onChange={(e) => setSubtitulo(e.target.value)}
                placeholder="Cuando Kutxi conoció a Robe"
                className="mt-1 w-full bg-transparent border border-divider focus:border-accent outline-none text-ink text-sm font-serif px-2 py-1.5"
              />
            </div>
          </div>
          <div className="mt-4 flex items-center gap-3 flex-wrap">
            <button
              type="button"
              disabled={busy || !url.trim() || !hasta.trim()}
              onClick={pedir}
              data-cursor="hover"
              className="font-mono text-[10px] tracking-[2px] uppercase border border-accent text-accent hover:bg-accent hover:text-white px-3 py-1.5 disabled:opacity-40"
            >
              {busy ? "…" : "pedir clip"}
            </button>
            <span className="font-mono text-[9px] text-ink-faint">
              máximo 60 s · nada de canales oficiales ni discográficas
            </span>
          </div>
          {error && (
            <p className="mt-2 font-mono text-[10px] text-red-400">{error}</p>
          )}
        </div>
      )}

      {cargando ? (
        <p className="font-mono text-[10px] tracking-[2px] uppercase text-ink-faint">
          cargando…
        </p>
      ) : clips.length === 0 ? (
        <p className="font-serif italic text-ink-faint text-sm">
          Todavía no has pedido ningún clip.
        </p>
      ) : (
        <ul className="divide-y divide-divider">
          {clips.map((c) => (
            <li key={c.id} className="py-3 flex gap-4 items-start flex-wrap">
              <div className="flex-1 min-w-[260px]">
                <div className="flex items-center gap-3 flex-wrap">
                  <span
                    className={`font-mono text-[9px] tracking-[2px] uppercase border px-1.5 py-0.5 ${ESTADO_COLOR[c.status] ?? ""}`}
                  >
                    {ESTADO_LABEL[c.status] ?? c.status}
                  </span>
                  <span className="font-mono text-[10px] text-ink-faint">
                    {Math.round(c.start_s)}–{Math.round(c.end_s)} s
                  </span>
                  {c.ig_media_id && (
                    <span className="font-mono text-[9px] text-accent">
                      publicado
                    </span>
                  )}
                </div>
                <p className="mt-1 font-serif text-ink text-[15px] leading-tight">
                  {c.video_title ?? c.url}
                </p>
                {/* La procedencia, siempre visible: es lo que se enseña si
                    alguien reclama. */}
                <p className="mt-0.5 font-mono text-[10px] text-ink-dim">
                  canal:{" "}
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
                  <a
                    href={c.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="hover:text-accent"
                  >
                    ver original ↗
                  </a>
                </p>
                {c.queue_item_id && (
                  <p className="mt-1 font-mono text-[10px] text-accent">
                    enlazado con la publicación #{c.queue_item_id}
                  </p>
                )}
                {c.retired_reason && (
                  <p className="mt-1 font-mono text-[10px] text-ink-faint">
                    retirado: {c.retired_reason}
                  </p>
                )}
                {c.error && (
                  <p className="mt-1 font-mono text-[10px] text-red-400">
                    {c.error.slice(0, 200)}
                  </p>
                )}
              </div>

              {c.url_cdn && c.status !== "retired" && (
                <video
                  src={c.url_cdn}
                  controls
                  playsInline
                  className="w-[150px] h-[266px] object-contain bg-black border border-divider shrink-0"
                />
              )}

              {c.status === "ready" && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => asignar(c)}
                  data-cursor="hover"
                  title="Enlaza el clip con una publicación: al prepararla se usará este vídeo, con su sonido"
                  className="font-mono text-[10px] tracking-[2px] uppercase border border-accent text-accent hover:bg-accent hover:text-white px-3 py-1.5 disabled:opacity-40 shrink-0"
                >
                  {c.queue_item_id ? "cambiar post" : "usar en un post"}
                </button>
              )}

              {c.status !== "retired" && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => retirar(c)}
                  data-cursor="hover"
                  title="Borra el post de Instagram y el fichero, y deja constancia del motivo"
                  className="font-mono text-[10px] tracking-[2px] uppercase border border-red-500/60 text-red-400 hover:bg-red-500 hover:text-white px-3 py-1.5 disabled:opacity-40 shrink-0"
                >
                  retirar
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
