import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // Tokens "Entre Interiores"
        bg: { DEFAULT: "#0d0b0a", deep: "#070605" },
        paper: { DEFAULT: "#15110f", hi: "#1c1714" },
        // ink-dim/faint subidos para mejorar legibilidad en párrafos largos
        // y etiquetas pequeñas. Los hex anteriores caían por debajo del
        // contraste WCAG cómodo sobre #0d0b0a.
        ink: { DEFAULT: "#ede4d3", dim: "#c4b8a0", faint: "#8d8270" },
        // accent subido a granate vivo: el #a83a3a original daba ratio
        // ~1.7:1 y se desvanecía en mini-labels mono uppercase. Ahora ~5:1
        // (AA pass), conserva el alma rojo-vino del proyecto.
        accent: { DEFAULT: "#e85050", bright: "#ff6b6b" },
        divider: {
          DEFAULT: "rgba(237,228,211,0.08)",
          strong: "rgba(237,228,211,0.15)",
        },
      },
      fontFamily: {
        serif: ["var(--font-serif)", "Cormorant Garamond", "Georgia", "serif"],
        mono: ["var(--font-mono)", "JetBrains Mono", "Courier New", "monospace"],
        hand: ["var(--font-hand)", "Caveat", "cursive"],
      },
      animation: {
        "fade-up": "fadeUp 600ms ease",
      },
      keyframes: {
        fadeUp: {
          from: { opacity: "0", transform: "translateY(10px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
