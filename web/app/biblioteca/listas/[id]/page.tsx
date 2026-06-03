import Link from "next/link";
import { notFound } from "next/navigation";
import PlaylistDetailClient from "@/components/PlaylistDetailClient";
import { apiFetch, ApiError } from "@/lib/api";
import type { PlaylistDetail } from "@/lib/playlists";

export const metadata = {
  robots: { index: false, follow: false },
};

export default async function PlaylistDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  let detail: PlaylistDetail;
  try {
    detail = await apiFetch<PlaylistDetail>(`/playlists/${id}`);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  return (
    <main className="px-5 md:px-14 py-10 md:py-16 max-w-[920px] mx-auto">
      <Link
        href="/biblioteca/listas"
        data-cursor="hover"
        className="font-mono text-[11px] tracking-[2px] uppercase text-ink-dim hover:text-ink"
      >
        ← Tus listas
      </Link>

      <header className="mt-6 mb-10">
        <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-2">
          lista
        </p>
        <h1 className="font-serif text-4xl md:text-[60px] text-ink leading-[0.95] tracking-[-1.5px]">
          {detail.name}
        </h1>
      </header>

      <PlaylistDetailClient id={detail.id} initialTracks={detail.tracks} />
    </main>
  );
}
