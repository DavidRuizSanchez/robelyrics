import Link from "next/link";
import YoutubeLink from "@/components/YoutubeLink";
import { HighlightQuery } from "@/lib/highlight";
import type { SemanticHit } from "@/lib/types";

export default function SemanticResultCard({
  hit,
  query,
}: {
  hit: SemanticHit;
  query: string;
}) {
  return (
    <article className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 hover:border-zinc-700 transition">
      {/* Snippet con la línea destacada en su contexto */}
      <div className="font-serif leading-relaxed">
        {hit.context_before.map((line, i) => (
          <p
            key={`b${i}`}
            className="text-zinc-500 italic text-base mb-0.5"
          >
            {line}
          </p>
        ))}

        <div className="border-l-4 border-amber-500/70 bg-amber-500/[0.06] pl-4 py-1 my-1.5 rounded-r">
          <p className="text-2xl md:text-3xl text-zinc-50 font-serif">
            <HighlightQuery text={hit.line_text} query={query} />
          </p>
        </div>

        {hit.context_after.map((line, i) => (
          <p
            key={`a${i}`}
            className="text-zinc-500 italic text-base mt-0.5"
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
        <span>({hit.album.year})</span>
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

      {hit.why && (
        <p className="mt-4 text-sm text-zinc-500 italic">
          <span className="text-zinc-400 not-italic">por qué encaja:</span>{" "}
          {hit.why}
        </p>
      )}

      {hit.fan_context && (
        <details className="mt-4 group">
          <summary className="cursor-pointer text-sm text-amber-400/80 hover:text-amber-300 select-none">
            Contexto del universo Robe
          </summary>
          <div className="mt-3 p-4 bg-zinc-950/60 border-l-2 border-amber-500/40 rounded text-sm text-zinc-300 leading-relaxed">
            {hit.fan_context}
          </div>
        </details>
      )}
    </article>
  );
}
