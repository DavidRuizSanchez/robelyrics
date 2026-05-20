import Link from "next/link";
import type { PublicTrackOut } from "@/lib/types";

type Props = {
  artistSlug: string;
  albumSlug: string;
  currentSlug: string;
  tracks: PublicTrackOut[];
};

// Navegación prev/next dentro del álbum. Aporta 2 inlinks adicionales por
// canción (anterior y siguiente) y crea cadenas de exploración para crawlers.
export default function TrackNav({
  artistSlug,
  albumSlug,
  currentSlug,
  tracks,
}: Props) {
  const idx = tracks.findIndex((t) => t.slug === currentSlug);
  if (idx === -1) return null;

  const prev = idx > 0 ? tracks[idx - 1] : null;
  const next = idx < tracks.length - 1 ? tracks[idx + 1] : null;

  if (!prev && !next) return null;

  return (
    <nav
      aria-label="Navegación entre canciones del álbum"
      className="mt-16 mb-8 grid grid-cols-1 md:grid-cols-2 gap-4 border-t border-divider pt-8"
    >
      {prev ? (
        <Link
          href={`/${artistSlug}/${albumSlug}/${prev.slug}`}
          data-cursor="hover"
          className="group block py-4 px-4 -mx-4 hover:bg-paper transition-colors"
        >
          <p className="font-mono text-[10px] tracking-[3px] uppercase text-ink-faint mb-2">
            ← Canción anterior
          </p>
          <p className="font-serif text-lg md:text-xl text-ink-dim group-hover:text-accent transition-colors leading-tight">
            {prev.title}
          </p>
        </Link>
      ) : (
        <div />
      )}
      {next ? (
        <Link
          href={`/${artistSlug}/${albumSlug}/${next.slug}`}
          data-cursor="hover"
          className="group block py-4 px-4 -mx-4 hover:bg-paper transition-colors md:text-right"
        >
          <p className="font-mono text-[10px] tracking-[3px] uppercase text-ink-faint mb-2">
            Canción siguiente →
          </p>
          <p className="font-serif text-lg md:text-xl text-ink-dim group-hover:text-accent transition-colors leading-tight">
            {next.title}
          </p>
        </Link>
      ) : (
        <div />
      )}
    </nav>
  );
}
