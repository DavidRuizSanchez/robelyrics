import Link from "next/link";
import type { PublicTrackOut } from "@/lib/types";

type Props = {
  artistSlug: string;
  albumSlug: string;
  albumTitle: string;
  currentSlug: string;
  tracks: PublicTrackOut[];
};

// Bloque "Otras canciones de este álbum" en la página de canción. Cada track
// del álbum recibe un inlink adicional desde cada una de sus hermanas → sube
// la mediana de inlinks por canción de 3 a ~12-15.
export default function RelatedSongs({
  artistSlug,
  albumSlug,
  albumTitle,
  currentSlug,
  tracks,
}: Props) {
  const siblings = tracks.filter((t) => t.slug !== currentSlug);
  if (siblings.length === 0) return null;

  return (
    <section className="mt-16">
      <h2 className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-5">
        Más canciones de {albumTitle}
      </h2>
      <ol className="space-y-1">
        {siblings.map((t, i) => (
          <li key={t.slug}>
            <Link
              href={`/${artistSlug}/${albumSlug}/${t.slug}`}
              data-cursor="hover"
              className="group flex items-baseline gap-4 py-2 px-4 -mx-4 hover:bg-paper transition-colors"
            >
              <span className="font-mono text-[11px] text-ink-faint tabular-nums w-8 text-right">
                {t.track_number ?? i + 1}
              </span>
              <span className="font-serif text-base md:text-lg text-ink-dim group-hover:text-accent transition-colors leading-tight">
                {t.title}
              </span>
            </Link>
          </li>
        ))}
      </ol>
    </section>
  );
}
