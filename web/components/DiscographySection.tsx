import Link from "next/link";
import AlbumCover from "@/components/AlbumCover";
import Watermark from "@/components/Watermark";
import { apiFetch } from "@/lib/api";
import type { Album, Artist } from "@/lib/types";

type AlbumWithArtist = Album & { artist: Artist };

async function fetchAllAlbums(): Promise<AlbumWithArtist[]> {
  const artists = await apiFetch<Artist[]>("/artists");
  const all: AlbumWithArtist[] = [];
  for (const a of artists) {
    const albums = await apiFetch<Album[]>(`/artists/${a.slug}/albums`);
    for (const al of albums) {
      all.push({ ...al, artist: a });
    }
  }
  // Orden por año asc, luego artista
  return all.sort((x, y) => x.year - y.year || x.artist.slug.localeCompare(y.artist.slug));
}

export default async function DiscographySection({
  variant = "summary",
}: {
  variant?: "summary" | "full";
}) {
  const albums = await fetchAllAlbums();

  return (
    <section
      id="disco-anchor"
      className="relative overflow-hidden border-t border-divider py-16 md:py-32"
    >
      <Watermark
        text="1989·2024"
        size="28vw"
        rotate={-90}
        bottom="40%"
        right="-12%"
        opacity={0.025}
      />

      <div className="px-5 md:px-14 mb-10 max-w-[1100px] mx-auto">
        <div className="flex items-center gap-3.5 mb-4">
          <span className="block w-7 h-px bg-accent" />
          <span className="font-mono text-[11px] tracking-[4px] uppercase text-accent">
            discografía
          </span>
        </div>
        <h2 className="font-serif text-4xl md:text-[68px] font-normal text-ink m-0 leading-[1] tracking-[-1.5px]">
          Treinta años
          <br />
          <em className="italic text-accent">de letras</em>.
        </h2>
        <p className="font-serif italic text-ink-dim text-base md:text-lg mt-4 max-w-[560px]">
          De <em>Rock Transgresivo</em> (1989) a{" "}
          <em>Se nos lleva el aire</em> (2024). Toca un disco para entrar.
        </p>
      </div>

      <div className="max-w-[1100px] mx-auto px-5 md:px-14">
        {albums.map((d) => (
          <Link
            key={`${d.artist.slug}-${d.slug}`}
            href={`/biblioteca/${d.artist.slug}/${d.slug}`}
            data-cursor="hover"
            className="group grid grid-cols-[44px_56px_1fr] md:grid-cols-[70px_64px_1fr_auto] gap-2.5 md:gap-6 items-center py-4 md:py-5 border-b border-divider transition-[padding] duration-200 ease-[cubic-bezier(.2,.8,.2,1)] hover:pl-2 md:hover:pl-4"
          >
            <span className="font-mono text-[11px] md:text-[13px] text-ink-faint tracking-[1px]">
              {d.year}
            </span>
            <AlbumCover
              coverUrl={d.cover_url}
              slug={d.slug}
              title={d.title}
              variant="sm"
            />
            <p className="font-serif text-[17px] md:text-[26px] text-ink m-0 leading-[1.2] transition-colors duration-200 group-hover:text-accent">
              {d.title}
            </p>
            <span className="hidden md:inline font-mono text-[10px] tracking-[2px] uppercase text-ink-faint">
              {d.artist.name}
            </span>
          </Link>
        ))}
      </div>

      {variant === "summary" && (
        <div className="text-center mt-10">
          <Link
            href="/biblioteca/discografia"
            data-cursor="hover"
            className="inline-block font-mono text-[11px] tracking-[3px] uppercase text-ink-dim hover:text-accent transition-colors"
          >
            ver discografía completa →
          </Link>
        </div>
      )}
    </section>
  );
}
