import Link from "next/link";
import { notFound } from "next/navigation";
import YoutubeLink from "@/components/YoutubeLink";
import { apiFetch, ApiError } from "@/lib/api";
import type { SongDetail } from "@/lib/types";

export default async function SongPage({
  params,
}: {
  params: Promise<{ artist: string; album: string; song: string }>;
}) {
  const { artist, album, song } = await params;

  let detail: SongDetail;
  try {
    detail = await apiFetch<SongDetail>(`/songs/${song}`);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  return (
    <main className="px-5 md:px-14 py-10 md:py-16 max-w-[1100px] mx-auto">
      <div className="flex items-center gap-2 font-mono text-[11px] tracking-[2px] uppercase text-ink-dim">
        <Link
          href={`/${artist}`}
          data-cursor="hover"
          className="hover:text-ink"
        >
          {detail.artist.name}
        </Link>
        <span className="opacity-50">·</span>
        <Link
          href={`/${artist}/${album}`}
          data-cursor="hover"
          className="hover:text-ink"
        >
          {detail.album.title}
        </Link>
        <span className="text-ink-faint">({detail.album.year})</span>
      </div>

      <div className="mt-6 mb-10 md:mb-14 flex flex-wrap items-center gap-5">
        <h1 className="font-serif text-4xl md:text-[68px] font-normal text-ink m-0 leading-none tracking-[-1.5px]">
          {detail.title}
        </h1>
        <YoutubeLink
          title={detail.title}
          artist={detail.artist.name}
          videoId={detail.youtube_id}
        />
      </div>

      <div className="grid lg:grid-cols-[1fr_300px] gap-10 lg:gap-16">
        <article className="space-y-1">
          {groupByStanza(detail.lines).map((stanza, i) => (
            <div key={i} className="mb-8">
              {stanza.map((line) => (
                <p
                  key={line.line_index}
                  className="font-serif text-[19px] md:text-[22px] leading-relaxed text-ink m-0"
                >
                  {line.text}
                </p>
              ))}
            </div>
          ))}
        </article>

        {detail.interpretation && (
          <aside className="lg:sticky lg:top-24 self-start bg-paper border-l-2 border-accent/40 p-5 text-sm">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-mono text-[10px] tracking-[2px] uppercase text-accent">
                Interpretación fan
              </h2>
              <ConfidenceBadge
                confidence={detail.interpretation_confidence}
              />
            </div>

            {detail.interpretation.themes.length > 0 && (
              <div className="mb-4">
                <p className="font-mono text-[9px] tracking-[2px] uppercase text-ink-faint mb-2">
                  Temas
                </p>
                <ul className="flex flex-wrap gap-1.5">
                  {detail.interpretation.themes.map((t, i) => (
                    <li
                      key={i}
                      className="bg-paper-hi px-2 py-0.5 text-ink-dim text-xs font-serif italic"
                    >
                      {t.theme}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {detail.interpretation.key_metaphors.length > 0 && (
              <div className="mb-4">
                <p className="font-mono text-[9px] tracking-[2px] uppercase text-ink-faint mb-2">
                  Metáforas
                </p>
                <ul className="space-y-2">
                  {detail.interpretation.key_metaphors.map((m, i) => (
                    <li key={i} className="font-serif italic text-[14px] leading-relaxed">
                      <span className="text-ink">«{m.phrase}»</span>{" "}
                      <span className="text-ink-faint not-italic">→</span>{" "}
                      <span className="text-ink-dim">{m.meaning}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {detail.interpretation.fan_consensus && (
              <div>
                <p className="font-mono text-[9px] tracking-[2px] uppercase text-ink-faint mb-2">
                  Consenso
                </p>
                <p className="font-serif italic text-ink-dim text-[14px] leading-relaxed">
                  {detail.interpretation.fan_consensus}
                </p>
              </div>
            )}
          </aside>
        )}
      </div>
    </main>
  );
}

function groupByStanza(lines: SongDetail["lines"]) {
  const out: SongDetail["lines"][] = [];
  let cur: SongDetail["lines"] = [];
  let prev = -1;
  for (const l of lines) {
    if (l.stanza_index !== prev && cur.length > 0) {
      out.push(cur);
      cur = [];
    }
    cur.push(l);
    prev = l.stanza_index;
  }
  if (cur.length > 0) out.push(cur);
  return out;
}

function ConfidenceBadge({
  confidence,
}: {
  confidence: SongDetail["interpretation_confidence"];
}) {
  if (!confidence) return null;
  const styles = {
    high: "text-accent",
    medium: "text-accent/70",
    low: "text-ink-faint",
  } as const;
  return (
    <span
      className={`font-mono text-[9px] tracking-[2px] uppercase ${styles[confidence]}`}
    >
      {confidence}
    </span>
  );
}
