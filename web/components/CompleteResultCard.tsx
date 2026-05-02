import Link from "next/link";
import YoutubeLink from "@/components/YoutubeLink";
import { HighlightQuery } from "@/lib/highlight";
import type { CompleteHit } from "@/lib/types";

export default function CompleteResultCard({
  hit,
  query,
}: {
  hit: CompleteHit;
  query: string;
}) {
  return (
    <article className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 hover:border-zinc-700 transition">
      <div className="font-serif leading-relaxed">
        {/* matched_line: lo que el usuario escribió, como pista */}
        <div className="border-l-4 border-amber-500/70 bg-amber-500/[0.06] pl-4 py-1 mb-2 rounded-r">
          <p className="text-lg md:text-xl text-zinc-300 italic">
            <HighlightQuery text={hit.matched_line} query={query} />
          </p>
        </div>
        {/* lo que viene después: lo importante */}
        {hit.continuation_lines.map((line, i) => (
          <p
            key={i}
            className="text-xl md:text-2xl text-zinc-100 pl-4"
          >
            {line}
          </p>
        ))}
      </div>

      <div className="mt-5 flex flex-wrap items-center gap-x-2 gap-y-2 text-sm text-zinc-400">
        <Link
          href={`/${hit.artist.slug}/${hit.album.slug}/${hit.song.slug}`}
          className="text-zinc-200 font-semibold hover:underline"
        >
          {hit.song.title}
        </Link>
        <span>·</span>
        <Link
          href={`/${hit.artist.slug}/${hit.album.slug}`}
          className="hover:underline"
        >
          {hit.album.title}
        </Link>
        {hit.album.year && <span>({hit.album.year})</span>}
        <span>·</span>
        <Link href={`/${hit.artist.slug}`} className="hover:underline">
          {hit.artist.name}
        </Link>
        <YoutubeLink
          title={hit.song.title}
          artist={hit.artist.name}
          videoId={hit.song.youtube_id}
          seconds={hit.start_seconds}
          size="sm"
        />
      </div>
    </article>
  );
}
