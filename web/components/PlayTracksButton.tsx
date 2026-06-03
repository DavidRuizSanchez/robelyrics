"use client";

import { useYoutubePlayer } from "@/lib/youtube-player-context";
import { toPlayerTrack, type PlaylistTrackOut } from "@/lib/playlists";

// Carga una lista de pistas en el reproductor flotante y la pone a sonar.
export default function PlayTracksButton({
  tracks,
  startIndex = 0,
  label = "Reproducir",
  className = "",
}: {
  tracks: PlaylistTrackOut[];
  startIndex?: number;
  label?: string;
  className?: string;
}) {
  const { playQueue } = useYoutubePlayer();
  if (tracks.length === 0) return null;
  return (
    <button
      type="button"
      data-cursor="hover"
      onClick={() => playQueue(tracks.map(toPlayerTrack), startIndex)}
      className={
        "inline-flex items-center gap-2 border border-accent bg-accent text-white " +
        "hover:bg-accent-bright font-mono text-[11px] tracking-[2.5px] uppercase " +
        "px-5 py-2.5 transition-colors rounded-sm " +
        className
      }
    >
      <svg viewBox="0 0 16 16" className="w-3.5 h-3.5 shrink-0" fill="currentColor" aria-hidden>
        <path d="M4 3l9 5-9 5V3z" />
      </svg>
      {label}
    </button>
  );
}
