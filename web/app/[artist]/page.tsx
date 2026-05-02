import Link from "next/link";
import { notFound } from "next/navigation";
import AlbumCover from "@/components/AlbumCover";
import { apiFetch, ApiError } from "@/lib/api";
import type { Album, Artist } from "@/lib/types";

const VALID = new Set(["extremoduro", "robe"]);

export default async function ArtistPage({
  params,
}: {
  params: Promise<{ artist: string }>;
}) {
  const { artist } = await params;
  if (!VALID.has(artist)) notFound();

  let albums: Album[] = [];
  let artistInfo: Artist | undefined;
  try {
    const all = await apiFetch<Artist[]>("/artists");
    artistInfo = all.find((a) => a.slug === artist);
    albums = await apiFetch<Album[]>(`/artists/${artist}/albums`);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  return (
    <main className="px-5 md:px-14 py-10 md:py-16 max-w-[1100px] mx-auto">
      <Link
        href="/"
        data-cursor="hover"
        className="font-mono text-[11px] tracking-[2px] uppercase text-ink-dim hover:text-ink"
      >
        ← inicio
      </Link>

      <div className="mt-6 flex items-center gap-3.5 mb-3">
        <span className="block w-7 h-px bg-accent" />
        <span className="font-mono text-[11px] tracking-[4px] uppercase text-accent">
          artista
        </span>
      </div>
      <h1 className="font-serif text-4xl md:text-[68px] font-normal text-ink m-0 leading-none tracking-[-1.5px]">
        {artistInfo?.name || artist}
      </h1>
      {artistInfo?.active_years && (
        <p className="font-mono text-[11px] tracking-[2px] text-ink-faint mt-2">
          {artistInfo.active_years}
        </p>
      )}

      {/* Grid de discos con portadas */}
      <div className="mt-12 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-6 md:gap-8">
        {albums.map((alb) => (
          <Link
            key={alb.slug}
            href={`/${artist}/${alb.slug}`}
            data-cursor="hover"
            className="group block"
          >
            <div className="relative">
              <AlbumCover
                coverUrl={alb.cover_url}
                slug={alb.slug}
                title={alb.title}
                variant="md"
                className="!w-full !h-auto aspect-square"
              />
            </div>
            <p className="mt-3 font-serif text-[17px] md:text-lg text-ink leading-[1.25] transition-colors group-hover:text-accent">
              {alb.title}
            </p>
            <p className="font-mono text-[10px] tracking-[2px] uppercase text-ink-faint mt-1">
              {alb.year} · {alb.kind}
            </p>
          </Link>
        ))}
      </div>
    </main>
  );
}
