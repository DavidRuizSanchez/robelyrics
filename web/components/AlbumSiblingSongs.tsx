import Link from "next/link";
import type { PublicTrackOut } from "@/lib/types";

type Props = {
  artistSlug: string;
  albumSlug: string;
  albumTitle: string;
  currentSlug: string;
  tracks: PublicTrackOut[];
  // Prefijo de ruta: "" para la web pública, "/biblioteca" para la zona privada.
  basePath?: string;
  // Pistas que ya enlaza otro bloque de la página (TrackNav): van como texto,
  // para no enlazar dos veces el mismo destino (lib/enlazado.ts).
  sinEnlace?: string[];
};

// Bloque "Otras canciones de este álbum" en la página de canción. Cada track
// del álbum recibe un inlink adicional desde cada una de sus hermanas → sube
// la mediana de inlinks por canción de 3 a ~12-15.
export default function AlbumSiblingSongs({
  artistSlug,
  albumSlug,
  albumTitle,
  currentSlug,
  tracks,
  basePath = "",
  sinEnlace = [],
}: Props) {
  const siblings = tracks.filter((t) => t.slug !== currentSlug);
  if (siblings.length === 0) return null;

  return (
    <section className="mt-16">
      <h2 className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-5">
        Más canciones de {albumTitle}
      </h2>
      <ol className="space-y-1">
        {siblings.map((t, i) => {
          const contenido = (
            <>
              <span className="font-mono text-[11px] text-ink-faint tabular-nums w-8 text-right">
                {t.track_number ?? i + 1}
              </span>
              <span className="font-serif text-base md:text-lg text-ink-dim group-hover:text-accent transition-colors leading-tight">
                {t.title}
              </span>
            </>
          );
          return (
            <li key={t.slug}>
              {sinEnlace.includes(t.slug) ? (
                <div className="flex items-baseline gap-4 py-2 px-4 -mx-4">{contenido}</div>
              ) : (
                <Link
                  href={`${basePath}/${artistSlug}/${albumSlug}/${t.slug}`}
                  data-cursor="hover"
                  className="group flex items-baseline gap-4 py-2 px-4 -mx-4 hover:bg-paper transition-colors"
                >
                  {contenido}
                </Link>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
