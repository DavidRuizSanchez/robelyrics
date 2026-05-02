"use client";

import { useYoutubePlayer } from "@/lib/youtube-player-context";

export default function YoutubeFloatingPlayer() {
  const { player, close } = useYoutubePlayer();
  if (!player) return null;

  const startAt =
    player.seconds != null ? Math.max(0, player.seconds - 5) : 0;
  const embedSrc = `https://www.youtube.com/embed/${player.videoId}?autoplay=1&start=${startAt}&rel=0`;
  const watchUrl = `https://www.youtube.com/watch?v=${player.videoId}${
    player.seconds != null ? `&t=${startAt}s` : ""
  }`;

  return (
    <div
      className="fixed bottom-4 right-4 w-[400px] max-w-[calc(100vw-2rem)] bg-zinc-950 border border-zinc-700 rounded-lg shadow-2xl z-50 overflow-hidden"
      role="dialog"
      aria-label="Reproductor YouTube"
    >
      <div className="flex items-center justify-between px-3 py-2 border-b border-zinc-800 bg-zinc-900/60">
        <div className="min-w-0 flex-1 mr-2">
          {player.title && (
            <p className="text-sm text-zinc-200 truncate font-serif">
              {player.title}
            </p>
          )}
          {player.artist && (
            <p className="text-xs text-zinc-500 truncate">{player.artist}</p>
          )}
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <a
            href={watchUrl}
            target="_blank"
            rel="noopener noreferrer"
            title="Abrir en YouTube"
            className="text-zinc-500 hover:text-red-400 p-1 rounded transition"
            aria-label="Abrir en YouTube"
          >
            <svg viewBox="0 0 20 20" className="w-4 h-4" fill="currentColor">
              <path d="M11 3a1 1 0 100 2h2.586l-6.293 6.293a1 1 0 101.414 1.414L15 6.414V9a1 1 0 102 0V4a1 1 0 00-1-1h-5z" />
              <path d="M5 5a2 2 0 00-2 2v8a2 2 0 002 2h8a2 2 0 002-2v-3a1 1 0 10-2 0v3H5V7h3a1 1 0 000-2H5z" />
            </svg>
          </a>
          <button
            onClick={close}
            title="Cerrar"
            className="text-zinc-500 hover:text-zinc-200 p-1 rounded transition"
            aria-label="Cerrar reproductor"
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

      <div className="aspect-video bg-black">
        <iframe
          key={`${player.videoId}-${startAt}`}
          width="100%"
          height="100%"
          src={embedSrc}
          title={player.title || "YouTube video"}
          frameBorder={0}
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
          allowFullScreen
        />
      </div>
    </div>
  );
}
