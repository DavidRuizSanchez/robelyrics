"use client";

import { useEffect, useRef } from "react";
import { useKaraoke } from "@/lib/karaoke-context";

/**
 * Línea de letra con sincronización karaoke.
 * - Si la línea es la activa (current second ≥ start_seconds y < siguiente start),
 *   se resalta con borde lateral granate y aumenta sutilmente de tamaño.
 * - Si ya pasó: opacidad reducida.
 * - Si está por venir: estilo neutro.
 * - Si la canción no tiene timestamps o el usuario no ha pulsado play, todas
 *   las líneas en estilo "neutro" sin highlight.
 *
 * Auto-scroll a la línea activa con throttle (no scroll en cada cambio).
 */
export default function LyricLine({
  text,
  startSeconds,
  nextStartSeconds,
}: {
  text: string;
  startSeconds: number | null;
  nextStartSeconds: number | null;
}) {
  const { currentSeconds, isPlaying } = useKaraoke();
  const ref = useRef<HTMLParagraphElement | null>(null);
  const wasActiveRef = useRef(false);

  // Determinar estado
  const sync = isPlaying && currentSeconds != null && startSeconds != null;
  let state: "neutral" | "past" | "active" | "future" = "neutral";
  if (sync) {
    const t = currentSeconds!;
    if (t >= startSeconds!) {
      if (nextStartSeconds == null || t < nextStartSeconds) {
        state = "active";
      } else {
        state = "past";
      }
    } else {
      state = "future";
    }
  }

  // Auto-scroll cuando pasa a activa
  useEffect(() => {
    const isActive = state === "active";
    if (isActive && !wasActiveRef.current && ref.current) {
      ref.current.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    wasActiveRef.current = isActive;
  }, [state]);

  const cls =
    state === "active"
      ? "text-ink scale-[1.02] border-l-2 border-accent pl-3 -ml-3"
      : state === "past"
      ? "text-ink-faint"
      : state === "future"
      ? "text-ink-dim"
      : "text-ink";

  return (
    <p
      ref={ref}
      className={`font-serif text-[19px] md:text-[22px] leading-relaxed m-0 transition-all duration-300 ease-out ${cls}`}
    >
      {text}
    </p>
  );
}
