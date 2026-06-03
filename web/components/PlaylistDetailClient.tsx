"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useYoutubePlayer } from "@/lib/youtube-player-context";
import { toPlayerTrack, type PlaylistTrackOut } from "@/lib/playlists";

// Cliente de la página de detalle de una lista manual: reproducir entera,
// reproducir desde una canción, quitar canciones y borrar la lista.
export default function PlaylistDetailClient({
  id,
  initialTracks,
}: {
  id: number;
  initialTracks: PlaylistTrackOut[];
}) {
  const router = useRouter();
  const { playQueue } = useYoutubePlayer();
  const [tracks, setTracks] = useState<PlaylistTrackOut[]>(initialTracks);

  function playFrom(i: number) {
    playQueue(tracks.map(toPlayerTrack), i);
  }

  async function remove(songId: number | null | undefined) {
    if (songId == null) return;
    setTracks((ts) => ts.filter((t) => t.song_id !== songId));
    await fetch(`/biblioteca/listas/api/${id}/songs/${songId}`, { method: "DELETE" });
  }

  async function deleteList() {
    if (!confirm("¿Borrar esta lista? No se puede deshacer.")) return;
    await fetch(`/biblioteca/listas/api/${id}`, { method: "DELETE" });
    router.push("/biblioteca/listas");
    router.refresh();
  }

  return (
    <>
      <div className="flex flex-wrap items-center gap-3 mb-8">
        {tracks.length > 0 ? (
          <button
            type="button"
            data-cursor="hover"
            onClick={() => playFrom(0)}
            className="inline-flex items-center gap-2 border border-accent bg-accent text-white hover:bg-accent-bright font-mono text-[11px] tracking-[2.5px] uppercase px-5 py-2.5 transition-colors rounded-sm"
          >
            <svg viewBox="0 0 16 16" className="w-3.5 h-3.5" fill="currentColor" aria-hidden>
              <path d="M4 3l9 5-9 5V3z" />
            </svg>
            Reproducir lista
          </button>
        ) : (
          <p className="font-serif italic text-ink-dim">
            Esta lista está vacía. Añade canciones desde su ficha.
          </p>
        )}
        <button
          type="button"
          data-cursor="hover"
          onClick={deleteList}
          className="font-mono text-[10px] tracking-[2px] uppercase text-ink-faint hover:text-accent transition-colors"
        >
          borrar lista
        </button>
      </div>

      <ol className="space-y-1">
        {tracks.map((t, i) => (
          <li
            key={`${t.song_slug}-${i}`}
            className="group flex items-center gap-3 py-2.5 px-4 -mx-4 hover:bg-paper transition-colors"
          >
            <button
              onClick={() => playFrom(i)}
              data-cursor="hover"
              aria-label={`Reproducir desde ${t.title}`}
              className="text-ink-faint group-hover:text-accent shrink-0 w-6 text-center"
            >
              <span className="group-hover:hidden font-mono text-[11px] tabular-nums">
                {String(i + 1).padStart(2, "0")}
              </span>
              <svg
                viewBox="0 0 16 16"
                className="w-3.5 h-3.5 hidden group-hover:inline-block mx-auto"
                fill="currentColor"
                aria-hidden
              >
                <path d="M4 3l9 5-9 5V3z" />
              </svg>
            </button>
            <Link
              href={`/biblioteca/${t.artist_slug}/${t.album_slug}/${t.song_slug}`}
              data-cursor="hover"
              className="flex-1 min-w-0"
            >
              <span className="font-serif text-[17px] md:text-[19px] text-ink group-hover:text-accent transition-colors block truncate">
                {t.title}
              </span>
              <span className="font-mono text-[10px] tracking-[1px] uppercase text-ink-faint">
                {t.artist}
              </span>
            </Link>
            <button
              onClick={() => remove(t.song_id)}
              data-cursor="hover"
              aria-label="Quitar de la lista"
              className="text-ink-faint hover:text-accent shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
            >
              <svg viewBox="0 0 20 20" className="w-4 h-4" fill="currentColor">
                <path d="M4 5h12v1H4V5zm2 2h8l-.7 9H6.7L6 7zm3-4h2l1 1h3v1H3V5h3l1-1z" />
              </svg>
            </button>
          </li>
        ))}
      </ol>
    </>
  );
}
