import Image from "next/image";

/**
 * Logo principal de Entre Interiores: Robe en bote con guitarra dentro de
 * una bomba esférica, ballenas saltando, sol+nube en el cielo, mecha
 * encendida arriba. Estilo line-art / grabado / tatuaje.
 *
 * Variantes:
 *   - "light" (por defecto): líneas crema #ede4d3 sobre transparente, ideal
 *     para nuestro fondo deep-black estándar.
 *   - "dark": líneas negras sobre transparente, para casos puntuales con
 *     fondo claro (ejemplo: cabecera de emails con fondo crema).
 *
 * Tamaños: la imagen base es 1254×1254. Servimos versiones pre-redimensionadas
 * a 64/128/256/512 para que el navegador no descargue 400 KB en una cabecera
 * pequeña. `next/image` optimiza adicionalmente a webp en runtime.
 */
type Variant = "light" | "dark";
type Size = number;

const SIZE_TO_FILE = (size: Size, variant: Variant): string => {
  // Elegimos el archivo más cercano al tamaño pedido (con DPR x2 en mente).
  // La versión "dark" sólo está en tamaño completo (uso esporádico).
  if (variant === "dark") return "/logo-bomba.png";
  if (size <= 64) return "/logo-bomba-light-128.png"; // 2x para retina
  if (size <= 128) return "/logo-bomba-light-256.png";
  if (size <= 256) return "/logo-bomba-light-512.png";
  return "/logo-bomba-light.png";
};

export default function LogoBomba({
  size = 96,
  variant = "light",
  className,
  priority,
}: {
  size?: Size;
  variant?: Variant;
  className?: string;
  /** Pasar `priority` para LCP (login, hero) · fuerza preload. */
  priority?: boolean;
}) {
  const src = SIZE_TO_FILE(size, variant);
  return (
    <Image
      src={src}
      alt="Entre Interiores"
      width={size}
      height={size}
      priority={priority}
      className={className}
      style={{ width: size, height: size }}
    />
  );
}
