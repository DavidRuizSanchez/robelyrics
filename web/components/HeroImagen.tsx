"use client";

import { useState } from "react";
import NextImage from "next/image";

// Imagen de cabecera de un post. Se pinta como siempre (recortada a la caja
// 16:9, con la atribución encima), salvo que resulte ser VERTICAL: un cartel
// recortado a 16:9 pierde justo lo que dice (el de Flores Amarillas 2027 se
// quedaba en la franja de «20 bandas»). Entonces se enseña entera, lo que sobra a
// los lados lo rellena la misma imagen difuminada y la atribución pasa debajo,
// porque encima tapaba la fecha del cartel en el móvil.
//
// Las medidas no se conocen hasta que carga (no se guardan en la BD), así que se
// decide en `onLoad`. Medido el 16-11-2026: de 34 cabeceras publicadas, 25 son
// cuadradas, 2 apaisadas y 1 vertical; las cuadradas y apaisadas no cambian.

export default function HeroImagen({
  src,
  alt,
  sizes,
  atribucion,
}: {
  src: string;
  alt: string;
  sizes: string;
  atribucion: string | null;
}) {
  const [vertical, setVertical] = useState(false);

  return (
    <figure className="mb-10 -mx-5 md:mx-0">
      <div className="relative aspect-[16/9] max-h-[60vh] overflow-hidden bg-bg">
        {vertical && (
          <NextImage
            src={src}
            alt=""
            aria-hidden
            fill
            sizes={sizes}
            className="object-cover blur-2xl scale-110 opacity-50"
          />
        )}
        <NextImage
          src={src}
          alt={alt}
          fill
          priority
          sizes={sizes}
          className={vertical ? "object-contain" : "object-cover"}
          onLoad={(e) => {
            const img = e.currentTarget;
            setVertical(img.naturalHeight > img.naturalWidth * 1.05);
          }}
        />
        {atribucion && !vertical && (
          <figcaption className="absolute bottom-0 right-0 bg-bg/75 backdrop-blur-sm px-2 py-1 font-mono text-[9px] tracking-[1px] text-ink-faint">
            {atribucion}
          </figcaption>
        )}
      </div>
      {atribucion && vertical && (
        <figcaption className="px-5 md:px-0 pt-2 text-right font-mono text-[9px] tracking-[1px] text-ink-faint">
          {atribucion}
        </figcaption>
      )}
    </figure>
  );
}
