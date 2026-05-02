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
  inkDim: "#a89c87",
  inkFaint: "#6b614f",
  accent: "#a83a3a",
  accentBright: "#c84a48",
  divider: "rgba(237,228,211,0.08)",
  dividerStrong: "rgba(237,228,211,0.15)",
} as const;

export const fonts = {
  serif: "var(--font-serif)",
  mono: "var(--font-mono)",
  hand: "var(--font-hand)",
} as const;
