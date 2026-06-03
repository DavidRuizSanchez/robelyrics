import Link from "next/link";
import CreatePlaylist from "@/components/CreatePlaylist";
import MoodPlaylist from "@/components/MoodPlaylist";
import { apiFetch } from "@/lib/api";
import type { PlaylistSummary } from "@/lib/playlists";

export const metadata = {
  title: "Listas de reproducción · Entre Interiores",
  robots: { index: false, follow: false },
};

export default async function ListasPage() {
  let playlists: PlaylistSummary[] = [];
  try {
    playlists = await apiFetch<PlaylistSummary[]>("/playlists");
  } catch {
    playlists = [];
  }

  return (
    <main className="px-5 md:px-14 py-10 md:py-16 max-w-[920px] mx-auto">
      <header className="mb-10">
        <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-3">
          la música, contigo
        </p>
        <h1 className="font-serif text-4xl md:text-[64px] text-ink leading-[0.95] tracking-[-1.5px]">
          Listas
        </h1>
        <p className="font-serif italic text-ink-dim text-lg mt-5 max-w-2xl leading-relaxed">
          Pon a sonar lo que quieras y cambia de página: la música no se corta.
          Móntate listas a mano o deja que el estado de ánimo elija por ti.
        </p>
      </header>

      <MoodPlaylist />

      <section className="mt-14">
        <h2 className="font-serif text-2xl md:text-3xl text-ink mb-2 leading-tight">
          Tus listas
        </h2>
        <p className="font-serif italic text-ink-dim text-[15px] mb-5">
          Las que te montas tú, a mano, canción a canción.
        </p>

        <div className="mb-7 max-w-xl">
          <CreatePlaylist />
        </div>

        {playlists.length === 0 ? (
          <p className="font-serif italic text-ink-faint">
            Todavía no tienes ninguna. Crea una arriba y ve añadiéndole canciones
            desde la ficha de cada una.
          </p>
        ) : (
          <ul className="grid sm:grid-cols-2 gap-3">
            {playlists.map((pl) => (
              <li key={pl.id}>
                <Link
                  href={`/biblioteca/listas/${pl.id}`}
                  data-cursor="hover"
                  className="group block border border-divider rounded-sm p-5 hover:border-accent transition-colors"
                >
                  <span className="font-serif text-xl text-ink group-hover:text-accent transition-colors block leading-tight">
                    {pl.name}
                  </span>
                  <span className="font-mono text-[10px] tracking-[2px] uppercase text-ink-faint mt-1 block">
                    {pl.track_count} {pl.track_count === 1 ? "canción" : "canciones"}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
