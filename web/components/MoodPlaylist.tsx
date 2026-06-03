"use client";

import { useState } from "react";
import { useYoutubePlayer } from "@/lib/youtube-player-context";
import { toPlayerTrack, type PlaylistTrackOut } from "@/lib/playlists";

// Frases de gancho. El usuario también puede escribir lo suyo. Lo que escribe
// se embebe y se cruza con la letra completa de cada canción (lyrics_full_v1).
const CHIPS = [
  "Tengo ganas de caña",
  "Estoy de bajón",
  "Melancolía de madrugada",
  "Rabia y mala hostia",
  "Amor y resaca",
  "Ganas de carretera",
];

export default function MoodPlaylist() {
  const { playQueue } = useYoutubePlayer();
  const [mood, setMood] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [count, setCount] = useState<number | null>(null);

  async function generate(q: string) {
    const text = q.trim();
    if (text.length < 2 || loading) return;
    setMood(text);
    setLoading(true);
    setError(null);
    setCount(null);
    try {
      const res = await fetch("/biblioteca/listas/api/mood", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mood: text }),
      });
      if (!res.ok) throw new Error();
      const data = (await res.json()) as { tracks: PlaylistTrackOut[] };
      const tracks = data.tracks || [];
      setCount(tracks.length);
      if (tracks.length > 0) {
        playQueue(tracks.map(toPlayerTrack), 0);
      } else {
        setError("No he encontrado nada que pegue con eso. Prueba con otras palabras.");
      }
    } catch {
      setError("No se pudo armar la lista. Reinténtalo en un momento.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="border border-divider rounded-sm p-6 md:p-8 bg-paper/40">
      <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-2">
        según cómo andes
      </p>
      <h2 className="font-serif text-2xl md:text-3xl text-ink mb-2 leading-tight">
        Dime cómo te sientes y te monto la lista
      </h2>
      <p className="font-serif italic text-ink-dim text-[15px] mb-5">
        Escríbelo a tu manera o tira de un atajo. Cruzo lo que dices con lo que
        dicen las canciones y te lleno la cola.
      </p>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          generate(mood);
        }}
        className="flex flex-col sm:flex-row gap-2 mb-4"
      >
        <input
          value={mood}
          onChange={(e) => setMood(e.target.value)}
          placeholder="p.ej. necesito desahogarme a gritos"
          maxLength={200}
          className="flex-1 bg-bg border border-divider rounded-sm px-4 py-2.5 font-serif text-ink placeholder:text-ink-faint focus:border-accent outline-none"
        />
        <button
          type="submit"
          disabled={loading || mood.trim().length < 2}
          data-cursor="hover"
          className="border border-accent bg-accent text-white hover:bg-accent-bright disabled:opacity-50 font-mono text-[11px] tracking-[2.5px] uppercase px-6 py-2.5 transition-colors rounded-sm"
        >
          {loading ? "armando…" : "montar lista"}
        </button>
      </form>

      <ul className="flex flex-wrap gap-2">
        {CHIPS.map((c) => (
          <li key={c}>
            <button
              type="button"
              onClick={() => generate(c)}
              disabled={loading}
              data-cursor="hover"
              className="font-serif italic text-ink-dim border border-divider rounded-full px-4 py-1.5 text-[14px] hover:border-accent hover:text-accent transition-colors disabled:opacity-50"
            >
              {c}
            </button>
          </li>
        ))}
      </ul>

      {error && (
        <p className="mt-4 font-mono text-[11px] tracking-[1px] text-accent">{error}</p>
      )}
      {count != null && count > 0 && (
        <p className="mt-4 font-mono text-[11px] tracking-[1px] text-ink-dim">
          Sonando ya: {count} canciones para «{mood}». Cambia de página, que la
          música no se corta.
        </p>
      )}
    </section>
  );
}
