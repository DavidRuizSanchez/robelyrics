import { SunMark } from "@/components/Logo";
import {
  DEFAULT_DISC_COLOR,
  DISCOGRAPHY_COLORS,
} from "@/lib/discography-display";

type Variant = "xs" | "sm" | "md" | "lg" | "xl";

const SIZE_MAP: Record<Variant, { px: number; sunSize: number }> = {
  xs: { px: 32, sunSize: 16 },
  sm: { px: 52, sunSize: 22 },
  md: { px: 140, sunSize: 56 },
  lg: { px: 240, sunSize: 88 },
  xl: { px: 320, sunSize: 120 },
};

/**
 * Portada del disco. Si hay `cover_url`, muestra la imagen real.
 * Si no, fallback al cuadrado degradado con SunMark (estética del prototipo).
 */
export default function AlbumCover({
  coverUrl,
  slug,
  title,
  variant = "md",
  className = "",
  isBack = false,
}: {
  coverUrl?: string | null;
  slug: string;
  title?: string;
  variant?: Variant;
  className?: string;
  /**
   * La imagen es la CONTRAPORTADA, no la portada. Pasa con «Tú en tu casa,
   * nosotros en la hoguera»: su portada original no circula y lo único
   * auténtico que hay es la trasera. Enseñarla está bien; rotularla «Portada
   * de…» no, y ese fue justo el fallo que dejó al disco sin imagen.
   */
  isBack?: boolean;
}) {
  const { px, sunSize } = SIZE_MAP[variant];

  if (coverUrl) {
    const que = isBack ? "Contraportada" : "Portada";
    return (
      <img
        src={coverUrl}
        alt={title ? `${que} de ${title}` : que}
        width={px}
        height={px}
        className={`block rounded shadow-[0_8px_20px_rgba(0,0,0,0.4)] object-cover ${className}`}
        style={{ width: px, height: px }}
        loading="lazy"
      />
    );
  }

  const color = DISCOGRAPHY_COLORS[slug] || DEFAULT_DISC_COLOR;
  return (
    <span
      className={`block rounded flex items-center justify-center shadow-[0_4px_10px_rgba(0,0,0,0.3)] ${className}`}
      style={{
        width: px,
        height: px,
        background: `linear-gradient(135deg, ${color}, ${color}cc)`,
      }}
    >
      <SunMark size={sunSize} color="rgba(255,235,200,0.85)" strokeWidth={1.4} />
    </span>
  );
}
