"use client";

import { useEffect, useRef, useState } from "react";
import { useKaraoke } from "@/lib/karaoke-context";

/**
 * Reproductor YouTube embed con sincronización al contexto Karaoke.
 * Carga la API IFrame de YouTube y hace polling cada 250ms del currentTime.
 *
 * Si el usuario aún no ha pulsado play, el contexto sigue null → las líneas
 * se renderizan en estado "neutro". En cuanto suena, las líneas reaccionan.
 */

declare global {
  interface Window {
    YT?: {
      Player: new (
        element: HTMLElement | string,
        options: Record<string, unknown>,
      ) => YTPlayer;
      PlayerState: {
        ENDED: number;
        PLAYING: number;
        PAUSED: number;
        BUFFERING: number;
        CUED: number;
      };
    };
    onYouTubeIframeAPIReady?: () => void;
  }
}

type YTPlayer = {
  getCurrentTime(): number;
  getPlayerState(): number;
  destroy(): void;
};

let apiLoadPromise: Promise<void> | null = null;
function loadYouTubeAPI(): Promise<void> {
  if (typeof window === "undefined") return Promise.resolve();
  if (window.YT && window.YT.Player) return Promise.resolve();
  if (apiLoadPromise) return apiLoadPromise;

  apiLoadPromise = new Promise((resolve) => {
    const tag = document.createElement("script");
    tag.src = "https://www.youtube.com/iframe_api";
    document.head.appendChild(tag);
    window.onYouTubeIframeAPIReady = () => resolve();
  });
  return apiLoadPromise;
}

export default function KaraokePlayer({
  videoId,
  className = "",
}: {
  videoId: string;
  className?: string;
}) {
  const { setCurrentSeconds, setIsPlaying } = useKaraoke();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const playerRef = useRef<YTPlayer | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let containerEl: HTMLElement | null = null;

    loadYouTubeAPI().then(() => {
      if (cancelled || !window.YT || !containerRef.current) return;
      containerEl = containerRef.current;
      // El YT.Player necesita un id, no un ref directamente
      const elId = `karaoke-player-${videoId}`;
      containerEl.id = elId;

      playerRef.current = new window.YT.Player(elId, {
        videoId,
        playerVars: {
          rel: 0,
          modestbranding: 1,
          playsinline: 1,
        },
        events: {
          onReady: () => setReady(true),
          onStateChange: (e: { data: number }) => {
            if (!window.YT) return;
            const playing = e.data === window.YT.PlayerState.PLAYING;
            setIsPlaying(playing);
            if (playing) startPolling();
            else stopPolling();
          },
        },
      });
    });

    return () => {
      cancelled = true;
      stopPolling();
      try {
        playerRef.current?.destroy();
      } catch {
        // ignore
      }
      setIsPlaying(false);
      setCurrentSeconds(null);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [videoId]);

  function startPolling() {
    if (pollRef.current) return;
    pollRef.current = setInterval(() => {
      try {
        const t = playerRef.current?.getCurrentTime();
        if (typeof t === "number") setCurrentSeconds(t);
      } catch {
        // ignore: el player puede no estar listo todavía
      }
    }, 250);
  }
  function stopPolling() {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }

  return (
    <div
      className={`relative aspect-video w-full bg-black overflow-hidden rounded ${className}`}
    >
      <div ref={containerRef} className="absolute inset-0" />
      {!ready && (
        <div className="absolute inset-0 flex items-center justify-center text-ink-faint font-mono text-[10px] tracking-[2px] uppercase">
          cargando reproductor…
        </div>
      )}
    </div>
  );
}
