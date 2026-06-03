import Link from "next/link";
import type { PublicRelatedSong } from "@/lib/types";

type Props = {
  songs: PublicRelatedSong[];
};

// Bloque "Canciones que tocan lo mismo": otras canciones del corpus (de
// cualquier disco) que comparten temas/conceptos/lugares con la actual.
// Refuerza el enlazado interno temático cross-album.
export default function RelatedSongs({ songs }: Props) {
  if (songs.length === 0) return null;

  return (
    <section className="mt-16">
      <h2 className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-5">
        Canciones que tocan lo mismo
      </h2>
      <ul className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {songs.map((s) => (
          <li key={s.url_path}>
            <Link
              href={s.url_path}
              data-cursor="hover"
              className="group block py-3 px-4 border border-divider hover:border-accent/60 hover:bg-paper transition-colors"
            >
              <span className="block font-serif text-lg text-ink-dim group-hover:text-accent transition-colors leading-tight">
                {s.title}
              </span>
              <span className="mt-1 block font-mono text-[10px] tracking-[2px] uppercase text-ink-faint">
                {s.album_title} · {s.year}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
