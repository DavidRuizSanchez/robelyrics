import Link from "next/link";
import { notFound } from "next/navigation";
import AlbumCover from "@/components/AlbumCover";
import KaraokePlayer from "@/components/KaraokePlayer";
import LyricLine from "@/components/LyricLine";
import SourcePills, { type SourceLite } from "@/components/SourcePills";
import { KaraokeProvider } from "@/lib/karaoke-context";
import { apiFetch, ApiError } from "@/lib/api";
import type { SongDetail } from "@/lib/types";

type SourceListOut = { total: number; items: SourceLite[] };

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

  // Interpolar timestamps: una línea sin start_seconds hereda el de la anterior
  // (evita "saltos" en el karaoke cuando lrclib/whisper saltó alguna línea).
  const linesEffective = withInterpolatedStarts(detail.lines);
  const stanzas = groupByStanza(linesEffective);
  const hasTimestamps = linesEffective.some((l) => l.effective_start != null);

  // Recopilar todos los source_ids citados en la interpretación y bulk-fetch
  // sus metadatos para que el sidebar pueda enlazarlos (cumple BY de CC-BY-NC-SA).
  const sourceMap: Record<number, SourceLite> = {};
  if (detail.interpretation) {
    const ids = new Set<number>();
    detail.interpretation.themes?.forEach((t) => t.source_ids?.forEach((id) => ids.add(id)));
    detail.interpretation.key_metaphors?.forEach((m) => m.source_ids?.forEach((id) => ids.add(id)));
    detail.interpretation.references?.forEach((r) => r.source_ids?.forEach((id) => ids.add(id)));
    detail.interpretation.fan_consensus_citations?.forEach((id) => ids.add(id));

    if (ids.size > 0) {
      try {
        const idsParam = Array.from(ids).join(",");
        const data = await apiFetch<SourceListOut>(
          `/sources?ids=${idsParam}&limit=500`,
        );
        for (const s of data.items) sourceMap[s.id] = s;
      } catch {
        /* sin fuentes resueltas: el sidebar simplemente no muestra pills */
      }
    }
  }

  return (
    <KaraokeProvider>
      <main className="px-5 md:px-14 py-10 md:py-16 max-w-[1200px] mx-auto">
        {/* Breadcrumb */}
        <div className="flex items-center gap-2 font-mono text-[11px] tracking-[2px] uppercase text-ink-dim">
          <Link
            href={`/biblioteca/${artist}`}
            data-cursor="hover"
            className="hover:text-ink"
          >
            {detail.artist.name}
          </Link>
          <span className="opacity-50">·</span>
          <Link
            href={`/biblioteca/${artist}/${album}`}
            data-cursor="hover"
            className="hover:text-ink"
          >
            {detail.album.title}
          </Link>
          <span className="text-ink-faint">({detail.album.year})</span>
        </div>

        {/* Header: portada + título + reproductor karaoke */}
        <header className="mt-6 mb-10 md:mb-14 grid grid-cols-1 md:grid-cols-[280px_1fr] gap-8 md:gap-10 items-start">
          <div>
            <AlbumCover
              coverUrl={detail.album.cover_url}
              slug={detail.album.slug}
              title={detail.album.title}
              variant="xl"
              className="!w-full !h-auto aspect-square"
            />
          </div>
          <div className="flex flex-col gap-5">
            {detail.track_number != null && (
              <p className="font-mono text-[11px] tracking-[2px] uppercase text-accent">
                · {String(detail.track_number).padStart(2, "0")}
              </p>
            )}
            <h1 className="font-serif text-4xl md:text-[68px] font-normal text-ink m-0 leading-[0.95] tracking-[-1.5px]">
              {detail.title}
            </h1>

            {detail.youtube_id ? (
              <KaraokePlayer videoId={detail.youtube_id} />
            ) : (
              <p className="font-mono text-[10px] tracking-[2px] uppercase text-ink-faint">
                sin video disponible
              </p>
            )}
            {detail.youtube_id && !hasTimestamps && (
              <p className="font-mono text-[9px] tracking-[2px] uppercase text-ink-faint">
                sin sincronización letra-audio
              </p>
            )}
          </div>
        </header>

        <div className="grid lg:grid-cols-[1fr_360px] gap-10 lg:gap-14">
          {/* Letra */}
          <article>
            <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-6">
              ─── verso a verso
            </p>
            {stanzas.map((stanza, i) => (
              <div key={i} className="mb-8">
                {stanza.map((line, j) => {
                  const idx = linesEffective.findIndex(
                    (l) => l.line_index === line.line_index,
                  );
                  // Próxima línea con effective_start
                  let nextStart: number | null = null;
                  for (let k = idx + 1; k < linesEffective.length; k++) {
                    if (linesEffective[k].effective_start != null) {
                      nextStart = linesEffective[k].effective_start;
                      break;
                    }
                  }
                  return (
                    <LyricLine
                      key={j}
                      text={line.text}
                      startSeconds={line.effective_start}
                      nextStartSeconds={nextStart}
                    />
                  );
                })}
              </div>
            ))}
          </article>

          {/* Sidebar interpretación */}
          {detail.interpretation && (
            <aside className="lg:sticky lg:top-24 self-start bg-paper border-l-2 border-accent/40 p-6">
              <div className="flex items-center justify-between mb-5">
                <h2 className="font-mono text-[11px] tracking-[2.5px] uppercase text-accent">
                  Interpretación fan
                </h2>
                <ConfidenceBadge confidence={detail.interpretation_confidence} />
              </div>

              {detail.interpretation.themes.length > 0 && (
                <div className="mb-6">
                  <p className="font-mono text-[10px] tracking-[2px] uppercase text-ink-faint mb-2.5">
                    Temas
                  </p>
                  <ul className="space-y-1.5">
                    {detail.interpretation.themes.map((t, i) => (
                      <li
                        key={i}
                        className="text-ink-dim text-[15px] font-serif italic"
                      >
                        <span className="bg-paper-hi px-2.5 py-0.5">{t.theme}</span>
                        {t.source_ids && (
                          <SourcePills sourceIds={t.source_ids} sources={sourceMap} />
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {detail.interpretation.key_metaphors.length > 0 && (
                <div className="mb-6">
                  <p className="font-mono text-[10px] tracking-[2px] uppercase text-ink-faint mb-2.5">
                    Metáforas
                  </p>
                  <ul className="space-y-3">
                    {detail.interpretation.key_metaphors.map((m, i) => (
                      <li
                        key={i}
                        className="font-serif italic text-[17px] leading-[1.55]"
                      >
                        <span className="text-ink">«{m.phrase}»</span>{" "}
                        <span className="text-ink-faint not-italic">→</span>{" "}
                        <span className="text-ink-dim">{m.meaning}</span>
                        {m.source_ids && (
                          <SourcePills sourceIds={m.source_ids} sources={sourceMap} />
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {detail.interpretation.references &&
                detail.interpretation.references.length > 0 && (
                  <div className="mb-6">
                    <p className="font-mono text-[10px] tracking-[2px] uppercase text-ink-faint mb-2.5">
                      Referencias
                    </p>
                    <ul className="space-y-2.5">
                      {detail.interpretation.references.map((r, i) => (
                        <li
                          key={i}
                          className="font-serif text-ink-dim text-[15px] leading-[1.55]"
                        >
                          <span className="font-mono text-[9px] tracking-[1.5px] uppercase text-accent mr-2">
                            {r.type}
                          </span>
                          {r.description}
                          {r.source_ids && (
                            <SourcePills sourceIds={r.source_ids} sources={sourceMap} />
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

              {detail.interpretation.fan_consensus && (
                <div>
                  <p className="font-mono text-[10px] tracking-[2px] uppercase text-ink-faint mb-2.5">
                    Consenso
                  </p>
                  <p className="font-serif italic text-ink-dim text-[17px] leading-[1.55]">
                    {detail.interpretation.fan_consensus}
                    {detail.interpretation.fan_consensus_citations && (
                      <SourcePills
                        sourceIds={detail.interpretation.fan_consensus_citations}
                        sources={sourceMap}
                      />
                    )}
                  </p>
                </div>
              )}

              {/* Atribución global de la capa privada */}
              <div className="mt-6 pt-4 border-t border-divider">
                <p className="font-mono text-[9px] tracking-[1.5px] uppercase text-ink-faint leading-relaxed">
                  Análisis derivado de fuentes fan ·{" "}
                  <Link
                    href="/biblioteca/atribuciones"
                    className="text-accent hover:underline"
                    data-cursor="hover"
                  >
                    atribuciones
                  </Link>
                </p>
              </div>
            </aside>
          )}
        </div>
      </main>
    </KaraokeProvider>
  );
}

type LineWithEffective = SongDetail["lines"][number] & {
  effective_start: number | null;
};

function withInterpolatedStarts(
  lines: SongDetail["lines"],
): LineWithEffective[] {
  let last: number | null = null;
  return lines.map((l) => {
    const eff = l.start_seconds ?? last;
    if (l.start_seconds != null) last = l.start_seconds;
    return { ...l, effective_start: eff };
  });
}

function groupByStanza(lines: LineWithEffective[]) {
  const out: LineWithEffective[][] = [];
  let cur: LineWithEffective[] = [];
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
