import Link from "next/link";
import { notFound } from "next/navigation";
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
    <main className="min-h-screen px-6 py-12 max-w-5xl mx-auto">
      <Link href="/" className="text-zinc-500 text-sm hover:text-zinc-300">
        ← buscar
      </Link>
      <h1 className="font-serif text-4xl md:text-5xl font-bold mt-4 mb-1">
        {artistInfo?.name || artist}
      </h1>
      {artistInfo?.active_years && (
        <p className="text-zinc-500">{artistInfo.active_years}</p>
      )}

      <ul className="mt-10 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {albums.map((alb) => (
          <li key={alb.slug}>
            <Link
              href={`/${artist}/${alb.slug}`}
              className="block bg-zinc-900 border border-zinc-800 rounded-lg p-5 hover:border-zinc-600 transition"
            >
              <div className="text-xs text-zinc-500 uppercase tracking-wide mb-1">
                {alb.year} · {alb.kind}
              </div>
              <div className="font-serif text-lg leading-tight text-zinc-100">
                {alb.title}
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
