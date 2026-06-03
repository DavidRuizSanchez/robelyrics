"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { loadYouTubeAPI, type YTPlayer } from "@/lib/youtube-api";
import { useYoutubePlayer } from "@/lib/youtube-player-context";

// Reproductor flotante PERSISTENTE de la zona privada. Vive en el layout de
// /biblioteca, así que sobrevive a la navegación cliente (la música no se corta
// al cambiar de página). Usa la YouTube IFrame API para detectar el final del
// vídeo y autoavanzar la cola.
export default function YoutubeFloatingPlayer() {
  const {
    current,
    queue,
    index,
    isPlaying,
    setIsPlaying,
    next,
    prev,
    jumpTo,
    removeAt,
    close,
    hasNext,
    hasPrev,
  } = useYoutubePlayer();

  const containerRef = useRef<HTMLDivElement | null>(null);
  const playerRef = useRef<YTPlayer | null>(null);
  const loadedIdRef = useRef<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // Mantenemos las acciones de cola en un ref para usarlas dentro de los
  // callbacks del player (que se crean una sola vez y capturarían valores
  // viejos si los cerrásemos directamente).
  const actionsRef = useRef({ next, setIsPlaying });
  actionsRef.current = { next, setIsPlaying };

  const [ready, setReady] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [duration, setDuration] = useState(0);
  const [showQueue, setShowQueue] = useState(false);
  const [videoHidden, setVideoHidden] = useState(false);

  function stopPolling() {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }
  function startPolling() {
    if (pollRef.current) return;
    pollRef.current = setInterval(() => {
      const p = playerRef.current;
      if (!p) return;
      try {
        setElapsed(p.getCurrentTime() || 0);
        setDuration(p.getDuration() || 0);
      } catch {
        // player aún no listo
      }
    }, 500);
  }

  // Crea el YT.Player una sola vez (cuando hay primera pista) y lo reutiliza.
  // Reacciona a los cambios de pista cargando el nuevo vídeo.
  useEffect(() => {
    if (!current) return;
    let cancelled = false;

    loadYouTubeAPI().then(() => {
      if (cancelled || !window.YT || !containerRef.current) return;

      if (!playerRef.current) {
        const elId = "yt-floating-player";
        containerRef.current.id = elId;
        playerRef.current = new window.YT.Player(elId, {
          videoId: current.videoId,
          playerVars: {
            autoplay: 1,
            rel: 0,
            modestbranding: 1,
            playsinline: 1,
            start: current.seconds != null ? Math.max(0, Math.floor(current.seconds) - 5) : 0,
          },
          events: {
            onReady: () => setReady(true),
            onStateChange: (e: { data: number }) => {
              if (!window.YT) return;
              const s = e.data;
              if (s === window.YT.PlayerState.ENDED) {
                actionsRef.current.next();
              } else if (s === window.YT.PlayerState.PLAYING) {
                actionsRef.current.setIsPlaying(true);
                startPolling();
              } else if (
                s === window.YT.PlayerState.PAUSED ||
                s === window.YT.PlayerState.CUED
              ) {
                actionsRef.current.setIsPlaying(false);
              }
            },
          },
        });
        loadedIdRef.current = current.videoId;
      }
    });

    return () => {
      cancelled = true;
    };
    // Solo en el primer current (crea el player). Las cargas posteriores van
    // en el efecto de abajo.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current ? true : false]);

  // Carga el vídeo cuando cambia la pista actual (cola: next/prev/jump).
  useEffect(() => {
    const p = playerRef.current;
    if (!p || !current) return;
    if (loadedIdRef.current === current.videoId && current.seconds == null) return;
    try {
      p.loadVideoById({
        videoId: current.videoId,
        startSeconds: current.seconds != null ? Math.max(0, Math.floor(current.seconds) - 5) : 0,
      });
      loadedIdRef.current = current.videoId;
      setElapsed(0);
      setDuration(0);
    } catch {
      // ignore
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current?.videoId, current?.seconds, ready]);

  useEffect(() => () => stopPolling(), []);

  if (!current) return null;

  function togglePlay() {
    const p = playerRef.current;
    if (!p || !window.YT) return;
    try {
      if (p.getPlayerState() === window.YT.PlayerState.PLAYING) p.pauseVideo();
      else p.playVideo();
    } catch {
      // ignore
    }
  }
  function handlePrev() {
    const p = playerRef.current;
    if (p && p.getCurrentTime() > 3) {
      p.seekTo(0, true);
    } else {
      prev();
    }
  }
  function handleSeek(e: React.ChangeEvent<HTMLInputElement>) {
    const p = playerRef.current;
    const v = Number(e.target.value);
    setElapsed(v);
    try {
      p?.seekTo(v, true);
    } catch {
      // ignore
    }
  }

  const songHref =
    current.artistSlug && current.albumSlug && current.songSlug
      ? `/biblioteca/${current.artistSlug}/${current.albumSlug}/${current.songSlug}`
      : null;

  const titleNode = (
    <p className="text-sm text-zinc-100 truncate font-serif leading-tight">
      {current.title}
    </p>
  );

  return (
    <div
      className="fixed bottom-4 right-4 w-[380px] max-w-[calc(100vw-2rem)] bg-zinc-950 border border-accent/50 rounded-lg shadow-2xl z-50 overflow-hidden"
      role="dialog"
      aria-label="Reproductor"
    >
      {/* Cabecera: sonando ahora + acciones */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-zinc-800 bg-zinc-900/60 gap-2">
        <div className="min-w-0 flex-1">
          <p className="font-mono text-[8px] tracking-[2px] uppercase text-accent mb-0.5">
            sonando ahora{queue.length > 1 ? ` · ${index + 1}/${queue.length}` : ""}
          </p>
          {songHref ? (
            <Link href={songHref} className="hover:text-accent block min-w-0" data-cursor="hover">
              {titleNode}
            </Link>
          ) : (
            titleNode
          )}
          {current.artist && (
            <p className="text-[11px] text-zinc-500 truncate">{current.artist}</p>
          )}
        </div>
        <div className="flex items-center gap-0.5 shrink-0">
          {queue.length > 1 && (
            <button
              onClick={() => setShowQueue((v) => !v)}
              title="Cola"
              aria-label="Ver la cola"
              className={`p-1.5 rounded transition ${showQueue ? "text-accent" : "text-zinc-500 hover:text-zinc-200"}`}
            >
              <svg viewBox="0 0 20 20" className="w-4 h-4" fill="currentColor">
                <path d="M3 5h11v2H3V5zm0 4h11v2H3V9zm0 4h7v2H3v-2zm13-1l4 2.5-4 2.5V12z" />
              </svg>
            </button>
          )}
          <button
            onClick={() => setVideoHidden((v) => !v)}
            title={videoHidden ? "Mostrar vídeo" : "Ocultar vídeo"}
            aria-label="Mostrar u ocultar el vídeo"
            className="p-1.5 rounded text-zinc-500 hover:text-zinc-200 transition"
          >
            <svg viewBox="0 0 20 20" className="w-4 h-4" fill="currentColor">
              {videoHidden ? (
                <path d="M2 5h16v10H2V5zm2 2v6h12V7H4z" />
              ) : (
                <path d="M3 9h14v2H3z" />
              )}
            </svg>
          </button>
          <button
            onClick={close}
            title="Cerrar"
            aria-label="Cerrar reproductor"
            className="p-1.5 rounded text-zinc-500 hover:text-zinc-200 transition"
          >
            <svg viewBox="0 0 20 20" className="w-4 h-4" fill="currentColor">
              <path
                fillRule="evenodd"
                d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
                clipRule="evenodd"
              />
            </svg>
          </button>
        </div>
      </div>

      {/* Panel de cola (toggle) */}
      {showQueue && queue.length > 1 && (
        <ol className="max-h-44 overflow-y-auto border-b border-zinc-800 bg-zinc-900/40 py-1">
          {queue.map((t, i) => (
            <li
              key={`${t.videoId}-${i}`}
              className={`flex items-center gap-2 px-3 py-1.5 text-[12px] ${i === index ? "text-accent" : "text-zinc-400 hover:text-zinc-200"}`}
            >
              <button
                onClick={() => jumpTo(i)}
                className="flex-1 text-left truncate"
                data-cursor="hover"
                title={t.title}
              >
                <span className="font-mono text-[10px] text-zinc-600 mr-2 tabular-nums">
                  {String(i + 1).padStart(2, "0")}
                </span>
                {t.title}
              </button>
              <button
                onClick={() => removeAt(i)}
                aria-label="Quitar de la cola"
                className="text-zinc-600 hover:text-red-400 shrink-0"
              >
                <svg viewBox="0 0 20 20" className="w-3.5 h-3.5" fill="currentColor">
                  <path d="M4 5h12v1H4V5zm2 2h8l-.7 9H6.7L6 7zm3-4h2l1 1h3v1H3V5h3l1-1z" />
                </svg>
              </button>
            </li>
          ))}
        </ol>
      )}

      {/* Vídeo (colapsable) */}
      <div className={`bg-black ${videoHidden ? "h-0" : "aspect-video"}`}>
        <div ref={containerRef} className="w-full h-full" />
      </div>

      {/* Controles de transporte */}
      <div className="px-3 py-2.5 bg-zinc-900/60">
        <input
          type="range"
          min={0}
          max={duration || 0}
          value={Math.min(elapsed, duration || 0)}
          onChange={handleSeek}
          aria-label="Progreso"
          className="w-full h-1 accent-[#a83a3a] cursor-pointer mb-2"
        />
        <div className="flex items-center justify-between">
          <span className="font-mono text-[10px] text-zinc-500 tabular-nums w-10">
            {fmt(elapsed)}
          </span>
          <div className="flex items-center gap-3">
            <button
              onClick={handlePrev}
              disabled={!hasPrev && elapsed <= 3}
              aria-label="Anterior"
              className="text-zinc-300 hover:text-accent disabled:text-zinc-700 transition"
            >
              <svg viewBox="0 0 20 20" className="w-5 h-5" fill="currentColor">
                <path d="M6 4h2v12H6V4zm9 0v12l-8-6 8-6z" />
              </svg>
            </button>
            <button
              onClick={togglePlay}
              aria-label={isPlaying ? "Pausar" : "Reproducir"}
              className="text-zinc-100 hover:text-accent transition"
            >
              {isPlaying ? (
                <svg viewBox="0 0 20 20" className="w-7 h-7" fill="currentColor">
                  <path d="M6 4h3v12H6V4zm5 0h3v12h-3V4z" />
                </svg>
              ) : (
                <svg viewBox="0 0 20 20" className="w-7 h-7" fill="currentColor">
                  <path d="M6 4l10 6-10 6V4z" />
                </svg>
              )}
            </button>
            <button
              onClick={next}
              disabled={!hasNext}
              aria-label="Siguiente"
              className="text-zinc-300 hover:text-accent disabled:text-zinc-700 transition"
            >
              <svg viewBox="0 0 20 20" className="w-5 h-5" fill="currentColor">
                <path d="M12 4h2v12h-2V4zM5 4l8 6-8 6V4z" />
              </svg>
            </button>
          </div>
          <span className="font-mono text-[10px] text-zinc-500 tabular-nums w-10 text-right">
            {fmt(duration)}
          </span>
        </div>
      </div>
    </div>
  );
}

function fmt(seconds: number): string {
  if (!seconds || !isFinite(seconds)) return "0:00";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}
