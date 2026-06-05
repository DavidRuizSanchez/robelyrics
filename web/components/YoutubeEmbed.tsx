"use client";

import { useState } from "react";

// Embed de YouTube con privacidad: muestra el thumbnail y solo carga el iframe
// (youtube-nocookie) al pulsar. Sin coste de red ni cookies hasta el clic.
export default function YoutubeEmbed({
  videoId,
  title,
}: {
  videoId: string;
  title?: string;
}) {
  const [play, setPlay] = useState(false);
  return (
    <div className="my-8 aspect-video w-full overflow-hidden border border-divider bg-black">
      {play ? (
        <iframe
          className="w-full h-full"
          src={`https://www.youtube-nocookie.com/embed/${videoId}?autoplay=1`}
          title={title || "Vídeo de YouTube"}
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
          allowFullScreen
        />
      ) : (
        <button
          type="button"
          onClick={() => setPlay(true)}
          data-cursor="hover"
          aria-label="Reproducir vídeo"
          className="group relative w-full h-full"
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={`https://i.ytimg.com/vi/${videoId}/hqdefault.jpg`}
            alt={title || "Vídeo"}
            className="w-full h-full object-cover opacity-80 transition group-hover:opacity-100"
          />
          <span className="absolute inset-0 flex items-center justify-center">
            <span className="font-mono text-[11px] tracking-[2px] uppercase text-white bg-accent/90 px-4 py-2">
              ▶ ver vídeo
            </span>
          </span>
        </button>
      )}
    </div>
  );
}
