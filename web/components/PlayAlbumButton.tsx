"use client";

import { useYoutubePlayer } from "@/lib/youtube-player-context";

type TrackInput = {
  slug: string;
  title: string;
  track_number?: number | null;
  youtube_id?: string | null;
};

// Botón que carga un disco (o lo que se le pase) en el reproductor flotante
// persistente y lo pone a sonar. `startSlug` permite arrancar por una canción
// concreta y seguir con el resto del disco en cola.
export default function PlayAlbumButton({
  artistSlug,
  albumSlug,
  artistName,
  tracks,
  startSlug,
  label = "Reproducir disco",
  className = "",
}: {
  artistSlug: string;
  albumSlug: string;
  artistName: string;
  tracks: TrackInput[];
  startSlug?: string;
  label?: string;
  className?: string;
}) {
  const { playQueue } = useYoutubePlayer();
  const playable = tracks.filter((t) => t.youtube_id);
  if (playable.length === 0) return null;

  const start = startSlug
    ? Math.max(0, playable.findIndex((t) => t.slug === startSlug))
    : 0;

  return (
    <button
      type="button"
      data-cursor="hover"
      onClick={() =>
        playQueue(
          playable.map((t) => ({
            videoId: t.youtube_id as string,
            title: t.title,
            artist: artistName,
            artistSlug,
            albumSlug,
            songSlug: t.slug,
          })),
          start,
        )
      }
      className={
        "inline-flex items-center gap-2 border border-accent bg-accent text-white " +
        "hover:bg-accent-bright font-mono text-[11px] tracking-[2.5px] uppercase " +
        "px-5 py-2.5 transition-colors rounded-sm " +
        className
      }
      title={label}
    >
      <svg viewBox="0 0 16 16" className="w-3.5 h-3.5 shrink-0" fill="currentColor" aria-hidden>
        <path d="M4 3l9 5-9 5V3z" />
      </svg>
      {label}
    </button>
  );
}
