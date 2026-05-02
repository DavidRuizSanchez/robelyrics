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
    <main className="min-h-screen px-6 py-12 max-w-3xl mx-auto">
      <div className="flex items-center gap-2 text-sm text-zinc-500">
        <Link href={`/${artist}`} className="hover:text-zinc-300">
          {detail.artist.name}
        </Link>
        <span>·</span>
        <Link href={`/${artist}/${album}`} className="hover:text-zinc-300">
          {detail.album.title}
        </Link>
        <span className="text-zinc-700">({detail.album.year})</span>
      </div>

      <div className="mt-4 mb-10 flex flex-wrap items-center gap-4">
        <h1 className="font-serif text-4xl md:text-5xl font-bold">
          {detail.title}
        </h1>
        <YoutubeLink
          title={detail.title}
          artist={detail.artist.name}
          videoId={detail.youtube_id}
        />
      </div>

      <div className="grid lg:grid-cols-[1fr_280px] gap-10">
        <article className="space-y-1">
          {groupByStanza(detail.lines).map((stanza, i) => (
            <div key={i} className="mb-6">
              {stanza.map((line) => (
                <p
                  key={line.line_index}
                  className="font-serif text-lg md:text-xl leading-relaxed text-zinc-100"
                >
                  {line.text}
                </p>
              ))}
            </div>
          ))}
        </article>

        {detail.interpretation && (
          <aside className="lg:sticky lg:top-12 self-start bg-zinc-900/60 border border-zinc-800 rounded-xl p-5 text-sm">
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-semibold text-zinc-200">
                Interpretación fan
              </h2>
              <ConfidenceBadge confidence={detail.interpretation_confidence} />
            </div>

            {detail.interpretation.themes.length > 0 && (
              <div className="mb-4">
                <p className="text-xs uppercase tracking-wide text-zinc-500 mb-1">
                  Temas
                </p>
                <ul className="flex flex-wrap gap-1.5">
                  {detail.interpretation.themes.map((t, i) => (
                    <li
                      key={i}
                      className="bg-zinc-800 px-2 py-0.5 rounded text-zinc-300 text-xs"
                    >
                      {t.theme}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {detail.interpretation.key_metaphors.length > 0 && (
              <div className="mb-4">
                <p className="text-xs uppercase tracking-wide text-zinc-500 mb-2">
                  Metáforas
                </p>
                <ul className="space-y-2">
                  {detail.interpretation.key_metaphors.map((m, i) => (
                    <li key={i}>
                      <span className="text-zinc-200 italic">«{m.phrase}»</span>{" "}
                      <span className="text-zinc-500">→</span>{" "}
                      <span className="text-zinc-400">{m.meaning}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {detail.interpretation.fan_consensus && (
              <div>
                <p className="text-xs uppercase tracking-wide text-zinc-500 mb-2">
                  Consenso
                </p>
                <p className="text-zinc-300 leading-relaxed">
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
    high: "bg-emerald-900/40 text-emerald-300",
    medium: "bg-amber-900/40 text-amber-300",
    low: "bg-zinc-800 text-zinc-400",
  } as const;
  return (
    <span className={`text-[10px] px-2 py-0.5 rounded uppercase tracking-wide ${styles[confidence]}`}>
      {confidence}
    </span>
  );
}
