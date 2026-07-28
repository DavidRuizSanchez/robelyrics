"use client";

import { useState } from "react";

/**
 * Vista previa fiel de cómo se verá el post en el feed de Instagram.
 *
 * Existe por una razón concreta: en el feed solo se lee el arranque del caption
 * antes del «… más». Durante meses los 40 posts publicados abrían con la misma
 * línea (`🕯️ Día N sin Robe`) y nadie lo notó revisando el panel, porque el
 * panel enseñaba la imagen y el caption por separado y nunca el corte real.
 *
 * Aquí se reproduce ese corte y se marca en granate lo único que verá alguien
 * que pase haciendo scroll.
 */

/** Lo que Instagram deja ver antes del «… más» (aprox., por caracteres). */
const CORTE = 125;

export type PreviewMedia = {
  position: number;
  kind: string;          // "image" | "video"
  role?: string | null;
  duration_s?: number | null;
};

type Props = {
  imageSrc: string | null;
  caption: string;
  username?: string;
  /** Piezas del post. Si hay más de una, se navega como carrusel. */
  media?: PreviewMedia[];
  /** Construye la URL de bytes de cada pieza. */
  mediaSrc?: (position: number) => string;
};

function partirEnElCorte(caption: string): { visible: string; resto: string } {
  const texto = caption ?? "";
  // Instagram corta por longitud, pero un salto de línea temprano también
  // esconde el resto: gana el que llegue antes.
  const salto = texto.indexOf("\n");
  const limite =
    salto >= 0 && salto < CORTE ? salto : Math.min(CORTE, texto.length);
  return { visible: texto.slice(0, limite), resto: texto.slice(limite) };
}

/** Pinta los #hashtags y las @menciones en el azul de enlace de Instagram. */
function conEnlaces(texto: string) {
  return texto.split(/([#@][\wÁÉÍÓÚÑáéíóúñ]+)/g).map((trozo, i) =>
    /^[#@]/.test(trozo) ? (
      <span key={i} className="text-[#4a7fb5]">
        {trozo}
      </span>
    ) : (
      <span key={i}>{trozo}</span>
    ),
  );
}

export default function InstagramPreview({
  imageSrc,
  caption,
  username = "entreinterioresrobe",
  media = [],
  mediaSrc,
}: Props) {
  const [abierto, setAbierto] = useState(false);
  const [slide, setSlide] = useState(0);
  const { visible, resto } = partirEnElCorte(caption);
  const hayMas = resto.trim().length > 0;

  const piezas = media.length > 0 ? media : [];
  const actual = piezas[Math.min(slide, piezas.length - 1)];
  const esVideo = actual?.kind === "video";
  // Los reels son 9:16; el resto, cuadrado.
  const alto = esVideo ? 568 : 320;

  return (
    <div className="w-[320px] shrink-0">
      <p className="font-mono text-[9px] tracking-[2px] uppercase text-ink-faint mb-2">
        así se verá en el feed
      </p>

      <div className="border border-divider bg-[#000] text-[#f5f5f5]">
        {/* Cabecera */}
        <div className="flex items-center gap-2 px-3 py-2.5">
          <div className="w-7 h-7 rounded-full bg-accent/30 border border-accent/50 shrink-0" />
          <span className="text-[13px] font-semibold leading-none">
            {username}
          </span>
        </div>

        {/* Media: vídeo, carrusel navegable o imagen suelta */}
        {piezas.length > 0 && mediaSrc ? (
          <div className="relative bg-[#111]" style={{ height: alto }}>
            {esVideo ? (
              <video
                key={actual.position}
                src={mediaSrc(actual.position)}
                controls
                loop
                muted
                playsInline
                className="w-[320px] object-contain bg-black"
                style={{ height: alto }}
              />
            ) : (
              /* eslint-disable-next-line @next/next/no-img-element */
              <img
                src={mediaSrc(actual.position)}
                alt={`Diapositiva ${slide + 1}`}
                className="w-[320px] object-cover"
                style={{ height: alto }}
              />
            )}

            {piezas.length > 1 && (
              <>
                <button
                  type="button"
                  onClick={() => setSlide((s) => Math.max(0, s - 1))}
                  disabled={slide === 0}
                  data-cursor="hover"
                  className="absolute left-1.5 top-1/2 -translate-y-1/2 w-7 h-7 rounded-full bg-black/60 text-[#f5f5f5] text-sm disabled:opacity-25"
                  aria-label="Anterior"
                >
                  ‹
                </button>
                <button
                  type="button"
                  onClick={() =>
                    setSlide((s) => Math.min(piezas.length - 1, s + 1))
                  }
                  disabled={slide === piezas.length - 1}
                  data-cursor="hover"
                  className="absolute right-1.5 top-1/2 -translate-y-1/2 w-7 h-7 rounded-full bg-black/60 text-[#f5f5f5] text-sm disabled:opacity-25"
                  aria-label="Siguiente"
                >
                  ›
                </button>
                <div className="absolute bottom-2 left-0 right-0 flex justify-center gap-1.5">
                  {piezas.map((p, i) => (
                    <span
                      key={p.position}
                      className={`w-1.5 h-1.5 rounded-full ${i === slide ? "bg-[#f5f5f5]" : "bg-[#f5f5f5]/40"}`}
                    />
                  ))}
                </div>
                <span className="absolute top-2 right-2 font-mono text-[10px] bg-black/60 text-[#f5f5f5] px-1.5 py-0.5 rounded">
                  {slide + 1}/{piezas.length}
                </span>
              </>
            )}
          </div>
        ) : imageSrc ? (
          /* eslint-disable-next-line @next/next/no-img-element */
          <img
            src={imageSrc}
            alt="Previsualización del post"
            className="w-[320px] h-[320px] object-cover"
          />
        ) : (
          <div className="w-[320px] h-[320px] bg-[#111] flex items-center justify-center text-center font-mono text-[9px] tracking-[1px] uppercase text-ink-faint p-4">
            sin material · pulsa «re-preparar»
          </div>
        )}

        {/* Barra de acciones (decorativa) */}
        <div className="flex items-center gap-4 px-3 pt-2.5 text-[17px] leading-none text-[#f5f5f5]">
          <span>♡</span>
          <span>💬</span>
          <span>↗</span>
          <span className="ml-auto">🔖</span>
        </div>

        {/* Caption con el corte real */}
        <div className="px-3 py-2 text-[13px] leading-[1.45]">
          <span className="font-semibold mr-1.5">{username}</span>
          <span className="whitespace-pre-wrap">
            {/* Lo único que se lee sin desplegar: resaltado. */}
            <span className="bg-accent/25 rounded-[2px]">
              {conEnlaces(visible)}
            </span>
            {hayMas && !abierto && (
              <>
                <span className="text-[#8e8e8e]">… </span>
                <button
                  type="button"
                  onClick={() => setAbierto(true)}
                  className="text-[#8e8e8e] hover:text-[#f5f5f5]"
                  data-cursor="hover"
                >
                  más
                </button>
              </>
            )}
            {hayMas && abierto && conEnlaces(resto)}
          </span>
        </div>
      </div>

      <p className="mt-2 font-mono text-[9px] leading-relaxed text-ink-faint">
        Lo resaltado es <span className="text-accent">todo</span> lo que lee
        quien pasa haciendo scroll: {visible.length} de {caption.length} car.
        {hayMas ? " El resto solo lo ve quien pulsa «más»." : ""}
      </p>
      {esVideo && (
        <p className="mt-1 font-mono text-[9px] text-ink-faint">
          Reel {actual?.duration_s ? `de ${Math.round(actual.duration_s)} s ` : ""}
          · sin audio (la música tiene derechos)
        </p>
      )}
    </div>
  );
}
