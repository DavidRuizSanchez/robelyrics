"use client";

import { useYoutubePlayer } from "@/lib/youtube-player-context";

// Botón YouTube. Al hacer click abre el reproductor flotante en la esquina.
// Si no hay videoId conocido, abre en nueva pestaña (búsqueda).
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
  const cls = size === "sm" ? "text-xs px-2 py-1" : "text-sm px-3 py-1.5";
  const iconCls = size === "sm" ? "w-3.5 h-3.5" : "w-4 h-4";
  const baseCls = `inline-flex items-center gap-1.5 bg-red-600/15 hover:bg-red-600/25 text-red-300 hover:text-red-200 rounded-md transition border border-red-900/40 ${cls}`;

  // Sin videoId conocido → fallback a búsqueda en nueva pestaña.
  if (!videoId) {
    const href = `https://www.youtube.com/results?search_query=${encodeURIComponent(`${title} ${artist}`)}`;
    return (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className={baseCls}
        title="Buscar en YouTube"
      >
        <YoutubeIcon className={iconCls} />
        Buscar YT
      </a>
    );
  }

  // Con videoId → abre el reproductor flotante in-page.
  const label =
    seconds != null
      ? `YouTube · ${formatTime(Math.max(0, seconds - 5))}`
      : "YouTube";
  const tooltip =
    seconds != null
      ? `Reproducir desde ${formatTime(seconds)}`
      : "Reproducir";

  return (
    <button
      type="button"
      onClick={() => open({ videoId, seconds, title, artist })}
      className={baseCls}
      title={tooltip}
    >
      <YoutubeIcon className={iconCls} />
      {label}
    </button>
  );
}

function YoutubeIcon({ className }: { className: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="currentColor" aria-hidden>
      <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z" />
    </svg>
  );
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}
