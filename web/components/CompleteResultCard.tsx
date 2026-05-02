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
    <article className="pb-8 border-b border-divider last:border-0">
      <p className="font-mono text-[10px] tracking-[2px] uppercase text-ink-faint m-0 mb-2">
        tú escribiste →
      </p>
      <p className="font-serif italic text-ink-dim text-[18px] md:text-[22px] m-0 pl-4 border-l-2 border-accent mb-5">
        <HighlightQuery text={hit.matched_line} query={query} />…
      </p>

      <div className="font-serif text-ink leading-[1.3] space-y-1">
        {hit.continuation_lines.map((line, i) => (
          <p key={i} className="text-[24px] md:text-[36px] m-0">
            {line}
          </p>
        ))}
      </div>

      <div className="mt-5 flex flex-wrap items-center gap-2.5 font-mono text-[10px] tracking-[1.5px] uppercase text-ink-dim">
        <Link
          href={`/${hit.artist.slug}/${hit.album.slug}/${hit.song.slug}`}
          data-cursor="hover"
          className="text-ink hover:text-accent transition-colors"
        >
          {hit.song.title}
        </Link>
        <span className="opacity-50">·</span>
        <Link
          href={`/${hit.artist.slug}/${hit.album.slug}`}
          data-cursor="hover"
          className="hover:text-ink transition-colors"
        >
          {hit.album.title}
        </Link>
        {hit.album.year && (
          <>
            <span className="opacity-50">·</span>
            <span>{hit.album.year}</span>
          </>
        )}
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
