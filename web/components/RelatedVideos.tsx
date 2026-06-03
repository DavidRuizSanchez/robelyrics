"use client";

import Image from "next/image";
import { useState } from "react";
import type { PublicRelatedVideo } from "@/lib/types";

// Bloque "Vídeos": colaboraciones, entrevistas y vídeos oficiales relacionados
// con la entidad de la página (distinto del vídeo canónico de cada canción).
// La card muestra el thumbnail de YouTube; al pulsar carga el iframe lazy
// (sin coste de red ni cookies de YouTube hasta el clic).

const KIND_LABEL: Record<string, string> = {
  collaboration: "Colaboración",
  interview: "Entrevista",
  official: "Vídeo oficial",
  live: "En directo",
};

function kindLabel(kind: string): string {
  return KIND_LABEL[kind] || "Vídeo";
}

function VideoCard({ video }: { video: PublicRelatedVideo }) {
  const [playing, setPlaying] = useState(false);
  return (
    <li>
      <div className="aspect-video w-full bg-black overflow-hidden relative rounded-sm border border-divider">
        {playing ? (
          <iframe
            src={`https://www.youtube.com/embed/${video.youtube_id}?autoplay=1&rel=0&modestbranding=1`}
            title={video.title}
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowFullScreen
            className="w-full h-full"
          />
        ) : (
          <button
            type="button"
            onClick={() => setPlaying(true)}
            data-cursor="hover"
            aria-label={`Reproducir: ${video.title}`}
            className="group absolute inset-0 w-full h-full"
          >
            <Image
              src={`https://i.ytimg.com/vi/${video.youtube_id}/hqdefault.jpg`}
              alt={video.title}
              fill
              sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw"
              className="object-cover transition-transform duration-500 group-hover:scale-[1.03]"
              unoptimized
            />
            <span className="absolute inset-0 bg-black/20 group-hover:bg-black/10 transition-colors" />
            <span className="absolute inset-0 flex items-center justify-center">
              <span className="font-serif text-2xl text-ink w-14 h-14 rounded-full bg-accent/90 flex items-center justify-center pl-1 shadow-lg group-hover:scale-110 transition-transform">
                ▶
              </span>
            </span>
          </button>
        )}
      </div>
      <p className="mt-3 font-mono text-[10px] tracking-[2px] uppercase text-ink-faint">
        {kindLabel(video.kind)}
      </p>
      <h3 className="mt-1 font-serif text-[17px] md:text-lg text-ink leading-[1.25]">
        {video.title}
      </h3>
    </li>
  );
}

export default function RelatedVideos({
  videos,
  heading = "Vídeos",
}: {
  videos: PublicRelatedVideo[] | undefined | null;
  heading?: string;
}) {
  if (!videos || videos.length === 0) return null;
  return (
    <section className="mt-16 border-t border-divider pt-10">
      <h2 className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-6">
        {heading}
      </h2>
      <ul className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-8">
        {videos.map((v) => (
          <VideoCard key={v.youtube_id} video={v} />
        ))}
      </ul>
    </section>
  );
}
