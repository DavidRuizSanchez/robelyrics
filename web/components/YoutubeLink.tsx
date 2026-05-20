"use client";

import { useYoutubePlayer } from "@/lib/youtube-player-context";

// Botón YouTube. Click → abre el reproductor flotante en la esquina.
// Sin videoId → fallback a búsqueda en nueva pestaña.
export default function YoutubeLink({
  title,
  artist,
  videoId,
  seconds,
  size = "md",
}: {
  title: string;
  artist: string;
  videoId?: string | null;
  seconds?: number | null;
  size?: "sm" | "md";
}) {
  const { open } = useYoutubePlayer();

  // Pastilla outline granate con fondo translúcido · visible pero coherente
  // con la paleta. Hover invierte (relleno granate, texto papel).
  const sizeCls =
    size === "sm"
      ? "text-[10px] px-2 py-1"
      : "text-[11px] px-3 py-1.5";
  const baseCls =
    "ml-auto inline-flex items-center gap-1.5 font-mono uppercase tracking-[1.5px] " +
    "border border-accent/60 bg-accent/15 text-accent " +
    "hover:bg-accent hover:text-white hover:border-accent " +
    "transition-colors rounded-sm";

  if (!videoId) {
    const href = `https://www.youtube.com/results?search_query=${encodeURIComponent(`${title} ${artist}`)}`;
    return (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        data-cursor="hover"
        className={`${baseCls} ${sizeCls}`}
        title="Buscar en YouTube"
      >
        <PlayIcon />
        Buscar YT
      </a>
    );
  }

  return (
    <button
      type="button"
      onClick={() => open({ videoId, seconds, title, artist })}
      data-cursor="hover"
      className={`${baseCls} ${sizeCls}`}
      title={
        seconds != null
          ? `Reproducir desde ${formatTime(seconds)}`
          : "Reproducir"
      }
    >
      <PlayIcon />
      {seconds != null
        ? formatTime(Math.max(0, seconds - 5))
        : "youtube"}
    </button>
  );
}

function PlayIcon() {
  return (
    <svg
      viewBox="0 0 16 16"
      className="w-3 h-3 shrink-0"
      fill="currentColor"
      aria-hidden
    >
      <path d="M5 3l8 5-8 5V3z" />
    </svg>
  );
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}
