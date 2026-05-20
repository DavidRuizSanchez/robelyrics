/**
 * Avatar tipográfico para personas sin fotografía libre disponible.
 *
 * Muchos miembros históricos de Extremoduro y de la banda solista de Robe
 * no tienen ninguna foto con licencia libre en repositorios públicos. En
 * lugar de un hueco "sin foto", se renderiza un monograma con sus iniciales
 * en la estética del sitio (serif Cormorant sobre fondo nocturno granate).
 * El monograma es determinista por slug, así cada persona mantiene siempre
 * el mismo tratamiento. No es una fotografía y no pretende serlo.
 */
import type { CSSProperties } from "react";

type Props = {
  name: string;
  slug: string;
};

function initials(name: string): string {
  const words = name
    .replace(/[«»"'.]/g, "")
    .split(/\s+/)
    .filter((w) => w.length > 0);
  if (words.length === 0) return "·";
  if (words.length === 1) return words[0].slice(0, 1).toUpperCase();
  return (words[0][0] + words[words.length - 1][0]).toUpperCase();
}

function hashSlug(slug: string): number {
  let h = 0;
  for (let i = 0; i < slug.length; i += 1) {
    h = (h * 31 + slug.charCodeAt(i)) >>> 0;
  }
  return h;
}

export default function PersonAvatar({ name, slug }: Props) {
  const variant = hashSlug(slug) % 3;
  // variante 0: iniciales granate · 1 y 2: iniciales papel
  const initialColor = variant === 0 ? "#a83a3a" : "#ede4d3";
  // variante 2: fondo con un velo granate más marcado
  const glow =
    variant === 2
      ? "rgba(168,58,58,0.22)"
      : "rgba(237,228,211,0.05)";

  return (
    <div
      aria-hidden="true"
      className="w-full h-full flex items-center justify-center select-none"
      style={
        {
          containerType: "size",
          background: `radial-gradient(ellipse at 50% 34%, ${glow}, #0d0b0a 72%)`,
        } as CSSProperties
      }
    >
      <span
        className="font-serif italic leading-none"
        style={{
          color: initialColor,
          fontSize: "clamp(2rem, 40cqw, 8rem)",
          letterSpacing: "-0.04em",
        }}
      >
        {initials(name)}
      </span>
    </div>
  );
}
