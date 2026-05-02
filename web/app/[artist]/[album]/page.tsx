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
    <main className="px-5 md:px-14 py-10 md:py-16 max-w-[920px] mx-auto">
      <Link
        href={`/${artist}`}
        data-cursor="hover"
        className="font-mono text-[11px] tracking-[2px] uppercase text-ink-dim hover:text-ink"
      >
        ← {detail.artist.name}
      </Link>

      <header className="mt-6 mb-12">
        <p className="font-mono text-[11px] tracking-[2px] uppercase text-ink-faint">
          {detail.year} · {detail.kind}
        </p>
        <h1 className="font-serif text-4xl md:text-[68px] font-normal text-ink mt-1 leading-none tracking-[-1.5px]">
          {detail.title}
        </h1>
      </header>

      <ol className="space-y-1">
        {detail.tracks.map((tr, i) => (
          <li key={tr.slug}>
            <Link
              href={`/${artist}/${album}/${tr.slug}`}
              data-cursor="hover"
              className="group flex items-baseline gap-4 py-3 px-4 -mx-4 hover:bg-paper transition-colors"
            >
              <span className="font-mono text-[11px] text-ink-faint tabular-nums w-8 text-right">
                {tr.track_number ?? i + 1}
              </span>
              <span className="font-serif text-[18px] md:text-[20px] flex-1 text-ink group-hover:text-accent transition-colors">
                {tr.title}
              </span>
              {tr.has_interpretation && (
                <span
                  className="text-accent text-xs"
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
