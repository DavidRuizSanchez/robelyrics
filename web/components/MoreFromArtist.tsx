import Link from "next/link";
import AlbumCover from "@/components/AlbumCover";
import type { PublicAlbumOut } from "@/lib/types";

type Props = {
  artistSlug: string;
  artistName: string;
  albums: PublicAlbumOut[];
  currentAlbumSlug?: string;
  /** Cuántos discos vecinos como máximo (cronológicos al actual). */
  max?: number;
};

// "Más discos de {artist}" en la página de álbum. Selección cronológica
// próxima al disco actual para crear navegación entre discos contiguos.
export default function MoreFromArtist({
  artistSlug,
  artistName,
  albums,
  currentAlbumSlug,
  max = 6,
}: Props) {
  const others = albums.filter((a) => a.slug !== currentAlbumSlug);
  if (others.length === 0) return null;

  // Si tenemos currentAlbumSlug, priorizar vecinos cronológicos.
  let picks = others;
  if (currentAlbumSlug) {
    const idx = albums.findIndex((a) => a.slug === currentAlbumSlug);
    if (idx !== -1) {
      const sorted = [...others].sort((a, b) => {
        const da = Math.abs(albums.findIndex((x) => x.slug === a.slug) - idx);
        const db = Math.abs(albums.findIndex((x) => x.slug === b.slug) - idx);
        return da - db;
      });
      picks = sorted.slice(0, max);
    }
  } else {
    picks = others.slice(0, max);
  }

  return (
    <section className="mt-20">
      <h2 className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-6">
        Más discos de {artistName}
      </h2>
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-6 md:gap-8">
        {picks.map((alb) => (
          <Link
            key={alb.slug}
            href={`/${artistSlug}/${alb.slug}`}
            data-cursor="hover"
            className="group block"
          >
            <AlbumCover
              coverUrl={alb.cover_url}
              slug={alb.slug}
              title={alb.title}
              variant="md"
              className="!w-full !h-auto aspect-square"
            />
            <p className="mt-3 font-serif text-[17px] md:text-lg text-ink leading-[1.25] transition-colors group-hover:text-accent">
              {alb.title}
            </p>
            <p className="font-mono text-[10px] tracking-[2px] uppercase text-ink-faint mt-1">
              {alb.year}
            </p>
          </Link>
        ))}
      </div>
    </section>
  );
}
