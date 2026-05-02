"use client";

import { useState } from "react";

export type SourceLite = {
  id: number;
  kind: string;
  url: string;
  title: string | null;
  author: string | null;
};

const KIND_SHORT: Record<string, string> = {
  blog: "blog",
  forum: "foro",
  youtube_transcript: "yt-transcript",
  youtube_comment: "yt-comment",
  genius_annotation: "genius",
  manual: "manual",
  book: "libro",
  thesis: "tesis",
};

/**
 * Renderiza los source_ids citados de una metáfora / tema / referencia como
 * pills minimal en línea. Click despliega un popover con el detalle (autor +
 * título + enlace al original). Cumple atribución BY de CC-BY-NC-SA y de las
 * citas LPI 32 para el resto de fuentes.
 */
export default function SourcePills({
  sourceIds,
  sources,
}: {
  sourceIds: number[];
  sources: Record<number, SourceLite>;
}) {
  const [openId, setOpenId] = useState<number | null>(null);

  const visible = sourceIds
    .map((id) => sources[id])
    .filter((s): s is SourceLite => Boolean(s));

  if (visible.length === 0) return null;

  return (
    <span className="inline-flex flex-wrap gap-1 ml-1.5 align-middle">
      {visible.map((s) => {
        const isOpen = openId === s.id;
        return (
          <span key={s.id} className="relative inline-block">
            <button
              type="button"
              data-cursor="hover"
              onClick={() => setOpenId(isOpen ? null : s.id)}
              className={`px-1.5 py-0.5 font-mono text-[9px] tracking-[1.5px] uppercase border transition-colors ${
                isOpen
                  ? "bg-accent text-white border-accent"
                  : "border-divider-strong text-ink-faint hover:border-accent hover:text-accent"
              }`}
              title={s.title || s.url}
            >
              {KIND_SHORT[s.kind] || s.kind}
            </button>

            {isOpen && (
              <span
                className="absolute z-30 left-0 top-full mt-1.5 w-72 bg-bg-deep border border-accent/40 p-3 text-left shadow-lg"
                onMouseLeave={() => setOpenId(null)}
              >
                <span className="block font-mono text-[9px] tracking-[1.5px] uppercase text-accent mb-1">
                  {s.kind.replace("_", " ")}
                </span>
                {s.title && (
                  <span className="block font-serif text-[14px] text-ink leading-snug mb-2 line-clamp-3">
                    {s.title}
                  </span>
                )}
                <span className="block font-mono text-[10px] tracking-[1px] text-ink-faint mb-2">
                  {s.author || "anónimo"}
                </span>
                <a
                  href={s.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  data-cursor="hover"
                  className="block font-mono text-[10px] tracking-[1.5px] uppercase text-accent hover:underline break-all"
                >
                  ver fuente original →
                </a>
              </span>
            )}
          </span>
        );
      })}
    </span>
  );
}
