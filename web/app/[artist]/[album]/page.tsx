import Link from "next/link";
import { notFound } from "next/navigation";
import { apiFetch, ApiError } from "@/lib/api";
import type { AlbumDetail } from "@/lib/types";

export default async function AlbumPage({
  params,
}: {
  params: Promise<{ artist: string; album: string }>;
}) {
  const { artist, album } = await params;

  let detail: AlbumDetail;
  try {
    detail = await apiFetch<AlbumDetail>(`/albums/${album}`);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  return (
    <main className="min-h-screen px-6 py-12 max-w-3xl mx-auto">
      <Link
        href={`/${artist}`}
        className="text-zinc-500 text-sm hover:text-zinc-300"
      >
        ← {detail.artist.name}
      </Link>

      <header className="mt-4 mb-10">
        <p className="text-sm text-zinc-500 uppercase tracking-wide">
          {detail.year} · {detail.kind}
        </p>
        <h1 className="font-serif text-4xl md:text-5xl font-bold mt-1">
          {detail.title}
        </h1>
      </header>

      <ol className="space-y-1">
        {detail.tracks.map((tr, i) => (
          <li key={tr.slug}>
            <Link
              href={`/${artist}/${album}/${tr.slug}`}
              className="flex items-baseline gap-4 px-4 py-3 rounded-lg hover:bg-zinc-900 transition"
            >
              <span className="text-zinc-600 tabular-nums w-8 text-right">
                {tr.track_number ?? i + 1}
              </span>
              <span className="font-serif text-lg flex-1 text-zinc-100">
                {tr.title}
              </span>
              {tr.has_interpretation && (
                <span
                  className="text-amber-500/80 text-xs"
                  title="Tiene interpretación fan"
                >
                  ◆
                </span>
              )}
            </Link>
          </li>
        ))}
      </ol>
    </main>
  );
}
