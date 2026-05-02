import Link from "next/link";
import { notFound } from "next/navigation";
import { SunMark } from "@/components/Logo";
import { apiFetch, ApiError } from "@/lib/api";
import {
  DEFAULT_DISC_COLOR,
  DISCOGRAPHY_COLORS,
} from "@/lib/discography-display";
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

      <ul className="mt-12">
        {albums.map((alb) => {
          const color = DISCOGRAPHY_COLORS[alb.slug] || DEFAULT_DISC_COLOR;
          return (
            <li key={alb.slug}>
              <Link
                href={`/${artist}/${alb.slug}`}
                data-cursor="hover"
                className="group grid grid-cols-[44px_36px_1fr] md:grid-cols-[70px_52px_1fr_auto] gap-2.5 md:gap-6 items-center py-4 md:py-5 border-b border-divider transition-[padding] duration-200 hover:pl-2 md:hover:pl-4"
              >
                <span className="font-mono text-[11px] md:text-[13px] text-ink-faint tracking-[1px]">
                  {alb.year}
                </span>
                <span
                  className="rounded flex items-center justify-center overflow-hidden w-8 h-8 md:w-11 md:h-11"
                  style={{
                    background: `linear-gradient(135deg, ${color}, ${color}cc)`,
                    boxShadow: "0 4px 10px rgba(0,0,0,0.3)",
                  }}
                >
                  <SunMark
                    size={20}
                    color="rgba(255,235,200,0.85)"
                    strokeWidth={1.4}
                  />
                </span>
                <p className="font-serif text-[17px] md:text-[26px] text-ink m-0 leading-[1.2] transition-colors group-hover:text-accent">
                  {alb.title}
                </p>
                <span className="hidden md:inline font-mono text-[10px] tracking-[2px] uppercase text-ink-faint">
                  {alb.kind}
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </main>
  );
}
