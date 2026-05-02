import Link from "next/link";
import YoutubeLink from "@/components/YoutubeLink";
import { HighlightQuery } from "@/lib/highlight";
import type { SemanticHit } from "@/lib/types";

export default function SemanticResultCard({
  hit,
  query,
  index,
}: {
  hit: SemanticHit;
  query: string;
  index: number;
}) {
  return (
    <article className="pb-8 border-b border-divider last:border-0">
      <div className="grid grid-cols-[auto_1fr] md:grid-cols-[60px_1fr] gap-3 md:gap-6 items-start">
        <span className="font-mono text-[11px] text-accent tracking-[2px] pt-3">
          0{index + 1}
        </span>
        <div className="font-serif">
          {hit.context_before.map((line, i) => (
            <p
              key={`b${i}`}
              className="font-serif italic text-ink-faint text-[15px] md:text-[17px] m-0"
            >
              {line}
            </p>
          ))}

          <p
            className={`font-serif font-normal text-ink leading-[1.2] tracking-[-0.5px] text-[28px] md:text-[42px] ${
              hit.context_before.length ? "my-2.5" : "mb-2.5"
            }`}
          >
            <HighlightQuery text={hit.line_text} query={query} />
          </p>

          {hit.context_after.map((line, i) => (
            <p
              key={`a${i}`}
              className="font-serif italic text-ink-faint text-[15px] md:text-[17px] m-0"
            >
              {line}
            </p>
          ))}

          <Meta hit={hit} />

          {hit.why && (
            <p className="mt-4 font-serif italic text-ink-dim text-[15px] leading-[1.6] max-w-[600px]">
              <span className="font-mono not-italic text-[9px] tracking-[2px] uppercase text-accent mr-2">
                encaja —
              </span>
              {hit.why}
            </p>
          )}

          {hit.fan_context && (
            <details className="mt-4 group">
              <summary
                data-cursor="hover"
                className="cursor-pointer font-mono text-[10px] tracking-[2px] uppercase text-accent/80 hover:text-accent select-none"
              >
                Contexto del universo Robe
              </summary>
              <div className="mt-3 p-4 bg-paper border-l-2 border-accent/40 text-[14px] text-ink-dim leading-relaxed font-serif italic">
                {hit.fan_context}
              </div>
            </details>
          )}
        </div>
      </div>
    </article>
  );
}

function Meta({ hit }: { hit: SemanticHit }) {
  return (
    <div className="mt-4 flex flex-wrap items-center gap-2.5 font-mono text-[10px] tracking-[1.5px] uppercase text-ink-dim">
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
      <span className="opacity-50">·</span>
      <span>{hit.album.year}</span>
      <YoutubeLink
        title={hit.song.title}
        artist={hit.artist.name}
        videoId={hit.song.youtube_id}
        seconds={hit.start_seconds}
        size="sm"
      />
    </div>
  );
}
