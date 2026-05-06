/**
 * Tokens de diseño "Entre Interiores".
 * Importa T cuando necesites la paleta como string en runtime
 * (SVG fill/stroke, gradientes inline, hover via JS).
 *
 * Para Tailwind, usa las clases bg-bg-deep, text-ink-dim, text-accent, etc.
 * (definidas en tailwind.config.ts).
 */

export const T = {
  bg: "#0d0b0a",
  bgDeep: "#070605",
  paper: "#15110f",
  paperHi: "#1c1714",
  ink: "#ede4d3",
  // dim subido (de #a89c87 ~6:1) para que párrafos largos cansen menos
  inkDim: "#c4b8a0",
  // faint subido (de #6b614f ~2.4:1) para etiquetas secundarias legibles
  inkFaint: "#8d8270",
  // accent subido (de #a83a3a ~1.7:1) manteniendo granate/vino, ahora ~5:1 (AA)
  accent: "#e85050",
  // accent-bright para hovers, ahora ~6.5:1
  accentBright: "#ff6b6b",
  divider: "rgba(237,228,211,0.08)",
  dividerStrong: "rgba(237,228,211,0.15)",
} as const;

export const fonts = {
  serif: "var(--font-serif)",
  mono: "var(--font-mono)",
  hand: "var(--font-hand)",
} as const;
